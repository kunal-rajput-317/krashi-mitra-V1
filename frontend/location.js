// ============================================================
// KrashiMitra — Device location opt-in
//
// The audience is almost entirely on phones, so — like every other
// farming app — we offer to use the device's location to personalise
// नज़दीकी मंडी भाव और मौसम. This is 100% free: the coordinates come from
// the browser's built-in Geolocation API (no key), and the readable
// "जिला, राज्य" comes from BigDataCloud's free, key-less client-side
// reverse-geocoder.
//
// UX (decided with the owner):
//   • Friendly in-app card FIRST → the native "Allow location?" popup
//     only fires when the farmer taps "चालू करें" (higher grant rate,
//     and browsers don't auto-block a gesture-triggered prompt).
//   • Ask ONCE per device, remember the choice, never nag. A declined
//     or denied page still works normally.
//
// Where it runs: loaded via the shell on home, mandi, weather, shop and
// the server-rendered /bhav/* + /product/* pages (bhav.py _header).
//
// Storage:
//   • Always → localStorage "km_geo" {status,lat,lon,location,ts}
//     status = granted | dismissed | denied
//   • Logged-in users → also POST /profile/location so it persists on
//     their users row (guests stay local-only).
//
// Public API (for pages that want to react):
//   window.KrashiLocation.get()   → the stored record (or null)
//   window.KrashiLocation.ask()   → (re)open the opt-in card
//   document 'km:location' event  → {lat, lon, location} on every resolve
// ============================================================
(function () {
  "use strict";

  var KEY     = "km_geo";
  var GEO_TTL = 7 * 24 * 3600 * 1000;   // silently refresh a granted spot after 7 days
  var shown   = false;                  // guard against a double-injected card

  // ── storage helpers ────────────────────────────────────────
  function readStore() {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); }
    catch (e) { return null; }
  }
  function writeStore(o) {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {}
  }
  function apiBase() {
    return window.KRASHIMITRA_API_BASE || "https://krashi-mitra-v1.onrender.com";
  }
  function token() {
    var t = localStorage.getItem("krishi_token");
    return (t && t !== "null" && t !== "undefined") ? t : null;
  }
  // Geolocation only works in a secure context — https, or localhost in dev.
  function secureEnough() {
    return location.protocol === "https:" ||
      ["localhost", "127.0.0.1", ""].indexOf(location.hostname) !== -1;
  }

  // ── reverse geocode: coords → "जिला, राज्य" (free, no key) ───
  function reverseGeocode(lat, lon) {
    var url = "https://api.bigdatacloud.net/data/reverse-geocode-client" +
      "?latitude=" + lat + "&longitude=" + lon + "&localityLanguage=hi";
    return fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var local = d.city || d.locality || "";
        var state = d.principalSubdivision || "";
        var loc   = [local, state].filter(Boolean).join(", ");
        return loc || d.countryName || "";
      })
      .catch(function () { return ""; });
  }

  // ── persist + broadcast ─────────────────────────────────────
  function persist(lat, lon, loc) {
    writeStore({ status: "granted", lat: lat, lon: lon, location: loc, ts: Date.now() });
    try {
      document.dispatchEvent(new CustomEvent("km:location",
        { detail: { lat: lat, lon: lon, location: loc } }));
    } catch (e) {}
    var t = token();
    if (t) {
      fetch(apiBase() + "/profile/location", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + t },
        body: JSON.stringify({ lat: lat, lon: lon, location: loc || null })
      }).catch(function () {});
    }
  }

  // ── native prompt → resolve → persist ───────────────────────
  // onDone(ok, loc)
  function requestPosition(onDone) {
    if (!navigator.geolocation) { onDone(false); return; }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = +pos.coords.latitude.toFixed(5);
        var lon = +pos.coords.longitude.toFixed(5);
        reverseGeocode(lat, lon).then(function (loc) {
          persist(lat, lon, loc);
          onDone(true, loc);
        });
      },
      function (err) {
        // code 1 = PERMISSION_DENIED → remember it so we never nag again.
        // Other errors (timeout / position unavailable) leave the door open.
        if (err && err.code === 1) writeStore({ status: "denied", ts: Date.now() });
        onDone(false);
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }
    );
  }

  // Already-allowed device: refresh coords quietly, no card.
  function silentRefresh() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = +pos.coords.latitude.toFixed(5);
        var lon = +pos.coords.longitude.toFixed(5);
        reverseGeocode(lat, lon).then(function (loc) { persist(lat, lon, loc); });
      },
      function () {},
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 3600000 }
    );
  }

  // ── the opt-in card ─────────────────────────────────────────
  function injectStyles() {
    if (document.getElementById("km-loc-style")) return;
    var css =
      "#km-loc-card{position:fixed;left:12px;right:12px;bottom:calc(84px + env(safe-area-inset-bottom,0px));" +
      "max-width:440px;margin:0 auto;z-index:99998;background:#fff;color:#173d28;" +
      "border:1px solid #d8e6dc;border-radius:18px;box-shadow:0 12px 34px rgba(16,50,30,.22);" +
      "padding:16px 16px 14px;font-family:inherit;transform:translateY(140%);opacity:0;" +
      "transition:transform .32s cubic-bezier(.2,.8,.2,1),opacity .32s}" +
      "#km-loc-card.km-in{transform:translateY(0);opacity:1}" +
      "#km-loc-card .km-loc-top{display:flex;gap:12px;align-items:flex-start}" +
      "#km-loc-card .km-loc-ic{font-size:26px;line-height:1;flex:0 0 auto;margin-top:1px}" +
      "#km-loc-card .km-loc-ttl{font-weight:800;font-size:15.5px;margin:0 0 3px}" +
      "#km-loc-card .km-loc-sub{font-size:13px;line-height:1.5;color:#4a6553;margin:0}" +
      "#km-loc-card .km-loc-row{display:flex;gap:9px;margin-top:14px}" +
      "#km-loc-card button{flex:1;border:0;border-radius:12px;padding:11px 12px;font:inherit;" +
      "font-weight:700;font-size:14px;cursor:pointer}" +
      "#km-loc-card .km-loc-ok{background:#1a7f43;color:#fff}" +
      "#km-loc-card .km-loc-ok:active{background:#156535}" +
      "#km-loc-card .km-loc-no{background:#eef3ef;color:#3c5648}" +
      "#km-loc-card .km-loc-ok[disabled]{opacity:.6;cursor:default}" +
      "@media (prefers-color-scheme:dark){#km-loc-card{background:#16241c;color:#e7f2ea;" +
      "border-color:#284d38}#km-loc-card .km-loc-sub{color:#a7c4b3}" +
      "#km-loc-card .km-loc-no{background:#22362b;color:#cfe3d6}}";
    var s = document.createElement("style");
    s.id = "km-loc-style";
    s.textContent = css;
    document.head.appendChild(s);
  }

  function removeCard() {
    var c = document.getElementById("km-loc-card");
    if (!c) return;
    c.classList.remove("km-in");
    setTimeout(function () { if (c.parentNode) c.parentNode.removeChild(c); }, 340);
  }

  function showCard() {
    if (shown || document.getElementById("km-loc-card")) return;
    if (!navigator.geolocation || !secureEnough()) return;
    shown = true;
    injectStyles();

    var card = document.createElement("div");
    card.id = "km-loc-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "स्थान चालू करें");
    card.innerHTML =
      '<div class="km-loc-top">' +
        '<div class="km-loc-ic">📍</div>' +
        '<div>' +
          '<p class="km-loc-ttl">अपना स्थान चालू करें</p>' +
          '<p class="km-loc-sub">नज़दीकी मंडी भाव और मौसम आपके क्षेत्र के अनुसार दिखाने के लिए।</p>' +
        '</div>' +
      '</div>' +
      '<div class="km-loc-row">' +
        '<button type="button" class="km-loc-no">अभी नहीं</button>' +
        '<button type="button" class="km-loc-ok">चालू करें</button>' +
      '</div>';
    document.body.appendChild(card);
    requestAnimationFrame(function () { card.classList.add("km-in"); });

    var okBtn = card.querySelector(".km-loc-ok");
    var noBtn = card.querySelector(".km-loc-no");

    noBtn.addEventListener("click", function () {
      writeStore({ status: "dismissed", ts: Date.now() });
      removeCard();
    });

    okBtn.addEventListener("click", function () {
      okBtn.disabled = true;
      okBtn.textContent = "प्रतीक्षा करें…";
      requestPosition(function (ok, loc) {
        if (ok) {
          card.querySelector(".km-loc-sub").textContent =
            loc ? ("✅ स्थान सेट: " + loc) : "✅ स्थान सेट हो गया।";
          card.querySelector(".km-loc-row").style.display = "none";
          card.querySelector(".km-loc-ttl").textContent = "धन्यवाद!";
          setTimeout(removeCard, 2500);
        } else {
          // denied or unavailable — bow out quietly, no re-nag
          removeCard();
        }
      });
    });
  }

  // ── boot ────────────────────────────────────────────────────
  function boot() {
    if (!secureEnough() || !navigator.geolocation) return;

    var s = readStore();
    if (s && s.status) {
      // Decision already made. Only touch it to refresh a stale grant.
      if (s.status === "granted" && (Date.now() - (s.ts || 0) > GEO_TTL)) silentRefresh();
      return;
    }

    // No decision yet. Peek at the permission state so we don't pop a
    // pointless card when the browser already knows the answer.
    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: "geolocation" }).then(function (p) {
        if (p.state === "granted")      silentRefresh();
        else if (p.state === "denied")  writeStore({ status: "denied", ts: Date.now() });
        else                            setTimeout(showCard, 1500);   // 'prompt'
      }).catch(function () { setTimeout(showCard, 1500); });
    } else {
      setTimeout(showCard, 1500);
    }
  }

  // ── public API ──────────────────────────────────────────────
  window.KrashiLocation = {
    get: readStore,
    ask: function () { shown = false; showCard(); }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
