// ============================================================
// KrashiMitra — KrashiBook (📒) — किसान की किताब
// ------------------------------------------------------------
// Replaces the old universal notification bell. One button in
// the header opens the farmer's personal book with three tabs:
//
//   🔔 सूचनाएं  — order/quote alerts (same cards + WhatsApp
//                 accept as the old bell) + today's weather alert
//   📖 इतिहास   — passbook-style ledger of every pre-book/order,
//                 plus the farmer's Bazar stats when logged in
//   💡 सुझाव    — personalized: today's mandi bhav for the
//                 farmer's own crops (from profile) + farming tip
//                 for their district; login/profile prompts when
//                 personalization data is missing
//
// Identity + data are shared with shop.html via the same
// localStorage keys (km_session_id, krishi_token, km_seen_status)
// and the /order/history API, so the badge stays in sync no
// matter which page the farmer is on. Personalization comes from
// GET /profile (district, primary_crop, crops_grown).
//
// Usage: include once per page, e.g.
//   <script src="krashibook.js"></script>
// (Not needed on shop.html, which ships its own native bell —
//  this script no-ops there to avoid a duplicate.)
// ============================================================
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  var WA_NUMBER = "919870951001"; // KrashiMitra WhatsApp
  function apiBase() {
    return window.KRASHIMITRA_API_BASE || "https://krashi-mitra-v1-oxdc.onrender.com";
  }
  // Location-aware path prefix (pages under /articles/ need to go up one level).
  function pagePrefix() {
    return location.pathname.indexOf("/articles/") !== -1 ? "../" : "";
  }
  function shopUrl()    { return pagePrefix() + "shop.html?orders=1"; }
  function loginUrl()   { return pagePrefix() + "login.html"; }
  function profileUrl() { return pagePrefix() + "profile.html"; }
  // Root-absolute, unlike its siblings: /bhav is backend-rendered, not a
  // static file next to this page, so pagePrefix()'s "../" would be wrong.
  function mandiUrl()   { return "/bhav"; }
  function weatherUrl() { return pagePrefix() + "weather.html"; }
  function bazarUrl()   { return pagePrefix() + "krashi_bajar.html"; }
  function fasalUrl()   { return pagePrefix() + "meri_fasal.html"; }

  // ── Identity + data (mirrors shop.html) ───────────────────
  function getSessionId() {
    var sid = localStorage.getItem("km_session_id");
    if (!sid) {
      sid = "km_" + Math.random().toString(36).substr(2, 8);
      localStorage.setItem("km_session_id", sid);
    }
    return sid;
  }
  function getToken() {
    var t = localStorage.getItem("krishi_token");
    return (t && t !== "null" && t !== "undefined") ? t : null;
  }

  function fetchOrderHistory(cb) {
    var token = getToken();
    var headers = {};
    var url;
    if (token) {
      headers["Authorization"] = "Bearer " + token;
      url = apiBase() + "/order/history";
    } else {
      url = apiBase() + "/order/history?session_id=" + encodeURIComponent(getSessionId());
    }
    fetch(url, { headers: headers })
      .then(function (r) { return r.json(); })
      .then(function (data) { cb((data && data.orders) || []); })
      .catch(function () { cb([]); });
  }

  function fetchProfile(cb) {
    var token = getToken();
    if (!token) { cb(null); return; }
    fetch(apiBase() + "/profile", { headers: { "Authorization": "Bearer " + token } })
      .then(function (r) { return r.json(); })
      .then(function (res) { cb((res && res.success && res.data) ? res.data : null); })
      .catch(function () { cb(null); });
  }

  // ── Helpers ───────────────────────────────────────────────
  function clean(s) { return String(s == null ? "" : s).replace(/[<>]/g, ""); }
  function lc(o) { return String(o.status || "").toLowerCase(); }
  function isQuoted(o) {
    return o.quote_total != null || String(o.status || "").toLowerCase() === "quoted";
  }

  var NOTIF_ALIAS = { prebook: "pending", verified: "quoted", canceled: "cancelled",
                      "out of order": "out of stock" };
  function stageKey(o) {
    var k = String(o.status || "pending").toLowerCase().trim();
    return NOTIF_ALIAS[k] || k;
  }
  var STATUS_NOTIF = {
    pending:     { chip: "⏳ दाम आना बाकी",  cls: "pending", msg: function (o) { return "हम आपके पिनकोड" + (o.pincode ? " " + clean(o.pincode) : "") + " पर dealer ढूँढ रहे हैं।"; } },
    booked:      { chip: "📝 बुक हो गया",    cls: "pending", msg: function () { return "आपकी प्री-बुक मिल गई — दाम तैयार हो रहा है।"; } },
    purchased:   { chip: "💳 ऑर्डर कन्फर्म", cls: "ok",      msg: function () { return "ऑर्डर पक्का हो गया — जल्द भेजा जाएगा।"; } },
    dispatched:  { chip: "🚚 भेज दिया गया",  cls: "ok",      msg: function (o) { return "आपका ऑर्डर रवाना हो गया" + (o.delivery_info ? " — " + clean(o.delivery_info) : "") + "।"; } },
    delivered:   { chip: "📦 डिलीवर हो गया", cls: "ok",      msg: function () { return "ऑर्डर डिलीवर हो गया — धन्यवाद! 🙏"; } },
    cancelled:   { chip: "❌ रद्द",          cls: "cancel",  msg: function () { return "यह ऑर्डर रद्द कर दिया गया है।"; } },
    unavailable: { chip: "🚫 उपलब्ध नहीं",   cls: "cancel",  msg: function () { return "यह उत्पाद अभी उपलब्ध नहीं है।"; } },
    // Distinct from unavailable: the dealer has simply run out, the product itself is fine.
    "out of stock": { chip: "📦 स्टॉक खत्म", cls: "cancel",  msg: function () { return "यह उत्पाद अभी स्टॉक में नहीं है।"; } },
  };

  function seenMap() {
    try { return JSON.parse(localStorage.getItem("km_seen_status") || "{}"); }
    catch (e) { return {}; }
  }
  function markAllSeen(orders) {
    var m = {};
    orders.forEach(function (o) { m[o.tracking_code] = lc(o); });
    try { localStorage.setItem("km_seen_status", JSON.stringify(m)); } catch (e) {}
  }
  function dot(isNew) { return isNew ? '<span class="km-book-new-dot"></span>' : ""; }
  // Old orders may have an empty product_name — never render a bare "· qty".
  function productLabel(o) {
    var name = clean(o.product_name).trim();
    if (!name) name = o.product_id ? "उत्पाद #" + o.product_id : "उत्पाद";
    return name + " · " + (o.quantity || 1);
  }
  function when(o, withYear) {
    if (!o.created_at) return "";
    try {
      var opts = withYear ? { day: "numeric", month: "short", year: "numeric" }
                          : { day: "numeric", month: "short" };
      return new Date(o.created_at).toLocaleDateString("hi-IN", opts);
    } catch (e) { return ""; }
  }

  // ── Crop → mandi commodity resolution ─────────────────────
  // Profile stores crops in English ("Wheat", "Rice", free-text
  // crops_grown). Mandi DB commodity strings come from data.gov
  // ("Paddy(Dhan)(Common)" etc.), so match by keywords the same
  // way mandi.html's tiles do.
  var CROP_DEFS = [
    { hi: "गेहूं",    emoji: "🌾", keys: ["wheat", "gehu"] },
    { hi: "धान",      emoji: "🌾", keys: ["paddy", "dhan", "rice"] },
    { hi: "गन्ना",    emoji: "🎋", keys: ["sugarcane", "ganna"] },
    { hi: "कपास",     emoji: "🧵", keys: ["cotton", "kapas"] },
    { hi: "मक्का",    emoji: "🌽", keys: ["maize", "corn", "makka"] },
    { hi: "सोयाबीन", emoji: "🫘", keys: ["soybean", "soyabean"] },
    { hi: "सरसों",    emoji: "🌼", keys: ["mustard", "sarson", "rai"] },
    { hi: "आलू",      emoji: "🥔", keys: ["potato", "aloo", "alu"] },
    { hi: "टमाटर",   emoji: "🍅", keys: ["tomato", "tamatar"] },
    { hi: "प्याज",    emoji: "🧅", keys: ["onion", "pyaj", "pyaz"] },
    { hi: "दाल",      emoji: "🫛", keys: ["pulses", "dal", "gram", "chana", "arhar", "lentil", "masoor", "urad", "moong"] },
    { hi: "मूंगफली", emoji: "🥜", keys: ["groundnut", "moongfali", "peanut"] },
    { hi: "मिर्च",    emoji: "🌶️", keys: ["chilli", "chili", "mirch"] },
    { hi: "केला",     emoji: "🍌", keys: ["banana", "kela"] },
    { hi: "आम",       emoji: "🥭", keys: ["mango", "aam"] },
    { hi: "बाजरा",    emoji: "🌾", keys: ["bajra", "millet"] },
    { hi: "जौ",       emoji: "🌾", keys: ["barley", "jau"] },
  ];
  function cropDef(name) {
    var n = String(name || "").toLowerCase().trim();
    if (!n) return null;
    for (var i = 0; i < CROP_DEFS.length; i++) {
      if (CROP_DEFS[i].keys.some(function (k) { return n.indexOf(k) !== -1 || k.indexOf(n) !== -1; })) return CROP_DEFS[i];
    }
    return { hi: name, emoji: "🌱", keys: [n] };
  }
  // Farmer's crop list from profile: primary first, then crops_grown, deduped.
  function farmerCrops(profile) {
    if (!profile) return [];
    var raw = [];
    if (profile.primary_crop) raw.push(profile.primary_crop);
    String(profile.crops_grown || "").split(",").forEach(function (c) {
      if (c.trim()) raw.push(c.trim());
    });
    var out = [], seenDefs = [];
    raw.forEach(function (name) {
      var def = cropDef(name);
      if (!def || seenDefs.indexOf(def) !== -1) return;
      seenDefs.push(def);
      out.push({ name: name, def: def });
    });
    return out.slice(0, 3);
  }
  function resolveCommodity(def, avail) {
    // Prefer exact match, then prefix, then shortest substring match —
    // otherwise "rice" resolves to "Beaten Rice" (sorted before "Rice").
    var best = null, bestScore = -1;
    (avail || []).forEach(function (c) {
      var cl = String(c).toLowerCase();
      def.keys.forEach(function (k) {
        var score = -1;
        if (cl === k) score = 3000;
        else if (cl.indexOf(k) === 0) score = 2000 - cl.length;
        else if (cl.indexOf(k) !== -1) score = 1000 - cl.length;
        if (score > bestScore) { bestScore = score; best = c; }
      });
    });
    return best;
  }

  // ── Shared state while the book is open ───────────────────
  var state = { orders: null, profile: null, profileDone: false, suggestLoaded: false };

  // ── TAB 1 · सूचनाएं (alerts) ──────────────────────────────
  function quoteCard(o, isNew) {
    var total = Number(o.quote_total || 0).toLocaleString("en-IN");
    return '<div class="km-book-card quoted">' +
      '<div class="km-book-card-head">' +
        '<span class="km-book-tracking">' + dot(isNew) + clean(o.tracking_code) + '</span>' +
        '<span class="km-book-chip quoted">💰 दाम तैयार</span>' +
      '</div>' +
      '<div class="km-book-product">' + productLabel(o) + '</div>' +
      '<div class="km-book-quote-total">पूरा दाम: ₹' + total + '</div>' +
      (o.delivery_info ? '<div class="km-book-line">🚚 ' + clean(o.delivery_info) + '</div>' : "") +
      (o.quote_note ? '<div class="km-book-line">📝 ' + clean(o.quote_note) + '</div>' : "") +
      '<button class="km-book-accept-btn" data-accept="' + clean(o.tracking_code) + '">' +
        '<img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" alt="WA" style="width:17px;height:17px;flex-shrink:0"> WhatsApp पर पक्का करें' +
      '</button>' +
    '</div>';
  }
  function statusCard(o, isNew) {
    var meta = STATUS_NOTIF[stageKey(o)] || { chip: clean(o.status || "अपडेट"), cls: "pending", msg: function () { return ""; } };
    var w = when(o);
    return '<div class="km-book-card">' +
      '<div class="km-book-card-head">' +
        '<span class="km-book-tracking">' + dot(isNew) + clean(o.tracking_code) + '</span>' +
        '<span class="km-book-chip ' + meta.cls + '">' + meta.chip + '</span>' +
      '</div>' +
      '<div class="km-book-product">' + productLabel(o) + '</div>' +
      '<div class="km-book-line">' + meta.msg(o) + '</div>' +
      (w ? '<div class="km-book-line" style="opacity:.6;font-size:11px;">📅 ' + w + '</div>' : "") +
    '</div>';
  }

  function renderAlerts() {
    var list = document.getElementById("km-book-tab-alerts");
    if (!list || state.orders == null) return;
    var orders = state.orders;
    var html = "";
    if (!orders.length) {
      html = '<div id="km-book-alerts-empty" class="km-book-empty"><span class="emoji">🔕</span>' +
        'अभी कोई सूचना नहीं।<br><span style="font-size:12px">प्री-बुक करें — हर अपडेट यहाँ दिखेगा।</span></div>';
    } else {
      var sorted = orders.slice().sort(function (a, b) {
        var qa = isQuoted(a) ? 1 : 0, qb = isQuoted(b) ? 1 : 0;
        if (qa !== qb) return qb - qa;
        return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      });
      var seen = seenMap();
      sorted.forEach(function (o) {
        var isNew = seen[o.tracking_code] !== lc(o);
        html += isQuoted(o) ? quoteCard(o, isNew) : statusCard(o, isNew);
      });
    }
    html += '<div id="km-book-dukan-alert"></div>';
    html += '<div id="km-book-crop-nudges"></div>';
    html += '<div id="km-book-weather-alert"></div>';
    html += '<button class="km-book-ghost-btn" data-href="' + shopUrl() + '">📋 सभी ऑर्डर देखें</button>';
    list.innerHTML = html;
    wireActions(list);
    loadDukanAlert();
    loadCropNudges();
    loadWeatherAlert();
  }

  // Dealer subscription state (/dukan/product). Parse-on-request, like the crop
  // nudges: /dukan/subscription recomputes from paid_until on every call, so
  // there is no scheduler to die quietly and no "reminder sent" flag to drift.
  //
  // This exists because a lapse was completely silent. services/buyers.py drops
  // a dealer from every farmer-facing surface the moment his month ends, and
  // nothing told him — his listing went dark and the first he knew was the
  // calls stopping. Renders nothing for farmers, who have no listing.
  function loadDukanAlert() {
    var slot = document.getElementById("km-book-dukan-alert");
    if (!slot) return;
    var token = getToken();
    if (!token) return;                       // guests own no listing
    fetch(apiBase() + "/dukan/subscription", { headers: { "Authorization": "Bearer " + token } })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res || !res.success || !res.data) return;
        var alerts = res.data.alerts || [];
        var slot2 = document.getElementById("km-book-dukan-alert");
        if (!slot2 || !alerts.length) return;
        var html = "";
        alerts.forEach(function (a) {
          var isNow = a.urgency === "now";
          var chip  = res.data.state === "lapsed" ? "⛔ बंद"
                    : res.data.state === "expiring" ? "⏳ खत्म हो रही"
                    : "💳 भुगतान बाकी";
          html +=
            '<div class="km-book-card ' + (isNow ? "warn" : "") + '">' +
              '<div class="km-book-card-head">' +
                '<span class="km-book-tracking">🏪 आपकी दुकान</span>' +
                '<span class="km-book-chip ' + (isNow ? "warnchip" : "ok") + '">' + chip + '</span>' +
              '</div>' +
              '<div class="km-book-product">' + clean(a.title_hi) + '</div>' +
              '<div class="km-book-line">' + clean(a.detail_hi) + '</div>' +
              '<button class="km-book-ghost-btn" data-href="/dukan/product" style="margin-top:8px">' +
                'अपनी दुकान देखें</button>' +
            '</div>';
        });
        slot2.innerHTML = html;
        // A lapsing subscription IS a notification — drop the empty card.
        var emptyEl = document.getElementById("km-book-alerts-empty");
        if (emptyEl) emptyEl.style.display = "none";
        wireActions(slot2);
      })
      .catch(function () {});
  }

  // Crop-task nudges from the farmer's saved crops (मेरी फसल). Parse-on-request:
  // /crop-calendar/nudges recomputes "due now / this week" live from crop_stages.json,
  // so no scheduler and no stale state. Logged-in only — guests keep their crops in
  // localStorage and see the calendar directly on the मेरी फसल page.
  function loadCropNudges() {
    var slot = document.getElementById("km-book-crop-nudges");
    if (!slot) return;
    var token = getToken();
    if (!token) {
      // Guest — reminders need a server-saved crop, so invite them to log in.
      slot.innerHTML =
        '<div class="km-book-card warn">' +
          '<div class="km-book-card-head">' +
            '<span class="km-book-tracking">🌱 फसल की याद</span>' +
            '<span class="km-book-chip ok">📅 मेरी फसल</span>' +
          '</div>' +
          '<div class="km-book-product">🔑 लॉगिन करें — फसल के काम की याद पाएं</div>' +
          '<div class="km-book-line">अपनी फसल और बुवाई तारीख जोड़ें, फिर लॉगिन करें — सिंचाई, खाद और यूरिया टॉप-ड्रेसिंग की याद ठीक समय पर यहाँ मिलेगी।</div>' +
          '<button class="km-book-ghost-btn" data-href="' + loginUrl() + '" style="margin-top:8px">लॉगिन / साइनअप करें</button>' +
        '</div>';
      wireActions(slot);
      return;
    }
    fetch(apiBase() + "/crop-calendar/nudges", { headers: { "Authorization": "Bearer " + token } })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res || !res.success || !res.data) return;
        var nudges = res.data.nudges || [];
        var slot2 = document.getElementById("km-book-crop-nudges");
        if (!slot2 || !nudges.length) return;
        var html = "";
        nudges.forEach(function (n) {
          var isNow     = n.urgency === "now";
          var isHarvest = n.kind === "harvest";
          var chip = isHarvest ? "🌾 कटाई नज़दीक" : (isNow ? "⏰ आज का काम" : "📅 इस हफ्ते");
          var href = isHarvest ? mandiUrl() : fasalUrl();
          var btn  = isHarvest ? "💰 मंडी भाव देखें" : "📅 मेरी फसल खोलें";
          html +=
            '<div class="km-book-card ' + (isNow ? "warn" : "") + '">' +
              '<div class="km-book-card-head">' +
                '<span class="km-book-tracking">' + clean(n.emoji) + ' ' + clean(n.crop_hi) + '</span>' +
                '<span class="km-book-chip ' + (isNow ? "warnchip" : "ok") + '">' + chip + '</span>' +
              '</div>' +
              '<div class="km-book-product">' + clean(n.title_hi) + '</div>' +
              (n.detail_hi ? '<div class="km-book-line">🌱 ' + clean(n.detail_hi) + '</div>' : "") +
              '<button class="km-book-ghost-btn" data-href="' + href + '" style="margin-top:8px">' + btn + '</button>' +
            '</div>';
        });
        slot2.innerHTML = html;
        // A due crop task IS a notification — drop the "कोई सूचना नहीं" empty card.
        var emptyEl = document.getElementById("km-book-alerts-empty");
        if (emptyEl) emptyEl.style.display = "none";
        wireActions(slot2);
      })
      .catch(function () {});
  }

  // Weather alert card for the farmer's own district (needs profile).
  function loadWeatherAlert() {
    var slot = document.getElementById("km-book-weather-alert");
    if (!slot) return;
    whenProfile(function (profile) {
      var district = profile && profile.district;
      if (!district) return; // no district → no weather alert, silently skip
      fetch(apiBase() + "/weather?district=" + encodeURIComponent(district))
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res || !res.success || !res.data || !document.getElementById("km-book-weather-alert")) return;
          var d = res.data;
          var rainy = (Number(d.rainfall) > 0) || /rain|storm|thunder|drizzle|बारिश|बूंदा/i.test(String(d.weather_condition || ""));
          var slot2 = document.getElementById("km-book-weather-alert");
          if (!slot2) return;
          slot2.innerHTML =
            '<div class="km-book-card ' + (rainy ? "warn" : "") + '">' +
              '<div class="km-book-card-head">' +
                '<span class="km-book-tracking">📍 ' + clean(d.district) + '</span>' +
                '<span class="km-book-chip ' + (rainy ? "warnchip" : "ok") + '">' + (rainy ? "🌧️ बारिश अलर्ट" : "🌤️ आज का मौसम") + '</span>' +
              '</div>' +
              '<div class="km-book-product">' + clean(d.weather_condition || "") + ' · ' + Math.round(Number(d.temperature) || 0) + '°C' +
                (d.humidity != null ? ' · नमी ' + d.humidity + '%' : '') + '</div>' +
              (d.farming_tip ? '<div class="km-book-line">🌱 ' + clean(d.farming_tip) + '</div>' : "") +
              '<button class="km-book-ghost-btn" data-href="' + weatherUrl() + '" style="margin-top:8px">🌦️ पूरा मौसम देखें</button>' +
            '</div>';
          wireActions(slot2);
        })
        .catch(function () {});
    });
  }

  // ── TAB 2 · इतिहास (passbook ledger) ──────────────────────
  function ledgerRow(o) {
    var meta = isQuoted(o)
      ? { chip: "💰 दाम तैयार", cls: "quoted" }
      : (STATUS_NOTIF[stageKey(o)] || { chip: clean(o.status || "—"), cls: "pending" });
    var amount = o.quote_total != null
      ? '<span class="km-book-ledger-amt">₹' + Number(o.quote_total || 0).toLocaleString("en-IN") + '</span>'
      : '<span class="km-book-ledger-amt muted">—</span>';
    return '<div class="km-book-ledger-row">' +
      '<div class="km-book-ledger-main">' +
        '<div class="km-book-product">' + productLabel(o) + '</div>' +
        '<div class="km-book-line" style="opacity:.65">📅 ' + (when(o, true) || "—") + ' · <span style="font-family:monospace">' + clean(o.tracking_code) + '</span></div>' +
      '</div>' +
      '<div class="km-book-ledger-side">' + amount + '<span class="km-book-chip ' + meta.cls + '">' + meta.chip + '</span></div>' +
    '</div>';
  }

  function renderHistory() {
    var list = document.getElementById("km-book-tab-history");
    if (!list || state.orders == null) return;
    var html = "";

    // Farmer identity strip (when profile is loaded)
    var p = state.profile;
    if (p) {
      var whoBits = [];
      if (p.full_name) whoBits.push("🧑‍🌾 " + clean(p.full_name));
      if (p.district) whoBits.push("📍 " + clean(p.district));
      var statBits = [];
      if (p.posts_count != null) statBits.push("📝 " + p.posts_count + " पोस्ट");
      if (p.followers_count != null) statBits.push("👥 " + p.followers_count + " फॉलोअर्स");
      if (whoBits.length || statBits.length) {
        html += '<div class="km-book-idcard">' +
          (whoBits.length ? '<div class="km-book-idcard-who">' + whoBits.join(" · ") + '</div>' : "") +
          (statBits.length ? '<div class="km-book-idcard-stats">' + statBits.join(" · ") + '</div>' : "") +
        '</div>';
      }
    }

    var orders = state.orders;
    if (!orders.length) {
      html += '<div class="km-book-empty"><span class="emoji">📖</span>' +
        'आपकी किताब अभी खाली है।<br><span style="font-size:12px">शॉप से प्री-बुक करें — हर ऑर्डर यहाँ दर्ज होगा।</span></div>';
    } else {
      var sorted = orders.slice().sort(function (a, b) {
        return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      });
      html += '<div class="km-book-ledger">';
      sorted.forEach(function (o) { html += ledgerRow(o); });
      html += '</div>';
    }
    html += '<button class="km-book-ghost-btn" data-href="' + shopUrl() + '">📋 सभी ऑर्डर देखें</button>';
    list.innerHTML = html;
    wireActions(list);
  }

  // ── TAB 3 · सुझाव (suggestions) ───────────────────────────
  function suggestLinkCard(emoji, title, sub, href) {
    return '<div class="km-book-card km-book-linkcard" data-href="' + href + '">' +
      '<div class="km-book-product">' + emoji + ' ' + title + '</div>' +
      '<div class="km-book-line">' + sub + '</div>' +
    '</div>';
  }

  function mandiPriceCard(crop, row) {
    var modal = Number(row.modal_price);
    var priceStr = isNaN(modal) ? clean(row.modal_price) : "₹" + modal.toLocaleString("en-IN");
    var chg = "";
    if (row.change_pct != null && row.change_pct !== "") {
      var v = Number(row.change_pct);
      if (!isNaN(v) && v !== 0) {
        chg = '<span class="km-book-chg ' + (v > 0 ? "up" : "down") + '">' + (v > 0 ? "▲" : "▼") + " " + Math.abs(v).toFixed(1) + "%</span>";
      }
    }
    return '<div class="km-book-card km-book-linkcard" data-href="' + mandiUrl() + '">' +
      '<div class="km-book-card-head">' +
        '<span class="km-book-product" style="margin:0">' + crop.def.emoji + ' ' + clean(crop.def.hi) + ' का भाव</span>' + chg +
      '</div>' +
      '<div class="km-book-quote-total" style="margin:4px 0">' + priceStr + ' <span style="font-size:12px;font-weight:600;color:#666">/क्विंटल</span></div>' +
      '<div class="km-book-line">🏪 ' + clean(row.market) + (row.district && row.district !== "-" ? ' · ' + clean(row.district) : '') +
        (row.date && row.date !== "-" ? ' · ' + clean(row.date) : '') + '</div>' +
    '</div>';
  }

  function fetchMandiFor(crop, avail, profile, cb) {
    var commodity = resolveCommodity(crop.def, avail);
    if (!commodity) { cb(null); return; }
    function q(params) {
      return fetch(apiBase() + "/shop/mandi?" + params)
        .then(function (r) { return r.json(); })
        .then(function (res) { return (res && res.prices && res.prices.length) ? res.prices[0] : null; });
    }
    var base = "commodity=" + encodeURIComponent(commodity);
    var district = profile && profile.district;
    var state = (profile && profile.state) || "Uttar Pradesh";
    // District first; fall back to the farmer's own state only — a random
    // market on the other side of the country is not a useful "suggestion".
    var first = district ? q(base + "&district=" + encodeURIComponent(district)) : Promise.resolve(null);
    first
      .then(function (row) { return row || q(base + "&state=" + encodeURIComponent(state)); })
      .then(function (row) { cb(row); })
      .catch(function () { cb(null); });
  }

  // ── मेरी फसल (crop calendar) cards ─────────────────────────
  // Summary is written to localStorage by meri_fasal.html on every
  // visit (works for guests too); falls back to the API when logged
  // in on a device that hasn't opened the page yet.
  function fasalCardHtml(c) {
    return '<div class="km-book-card km-book-linkcard" data-href="' + fasalUrl() + '">' +
      '<div class="km-book-card-head">' +
        '<span class="km-book-product" style="margin:0">' + c.emoji + ' ' + clean(c.name_hi) + '</span>' +
        '<span class="km-book-chip ok">दिन ' + c.day + '</span>' +
      '</div>' +
      (c.stage_hi ? '<div class="km-book-line">🌿 अवस्था: ' + clean(c.stage_hi) + '</div>' : '') +
      (c.next_task
        ? '<div class="km-book-line">📌 अगला काम: <b>' + clean(c.next_task) + '</b>' +
          (c.next_date ? ' (' + new Date(c.next_date + 'T00:00:00').toLocaleDateString('hi-IN', { day: 'numeric', month: 'short' }) + ')' : '') + '</div>'
        : '<div class="km-book-line">इस हफ्ते कोई खास काम नहीं — नज़र बनाए रखें।</div>') +
    '</div>';
  }
  function loadFasalCards() {
    var slot = document.getElementById("km-book-fasal-slot");
    if (!slot) return;
    function render(items) {
      var slot2 = document.getElementById("km-book-fasal-slot");
      if (!slot2 || !items || !items.length) return;
      var html = '<div class="km-book-section-title">🌱 मेरी फसल — इस हफ्ते</div>';
      items.slice(0, 3).forEach(function (c) { html += fasalCardHtml(c); });
      slot2.innerHTML = html;
      wireActions(slot2);
    }
    var cached = null;
    try { cached = JSON.parse(localStorage.getItem("km_fasal_summary") || "null"); } catch (e) {}
    if (cached && cached.length) { render(cached); return; }
    var token = getToken();
    if (!token) return;
    fetch(apiBase() + "/crop-calendar/my", { headers: { "Authorization": "Bearer " + token } })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        var crops = (res && res.data && res.data.crops) || [];
        render(crops.filter(function (t) { return t.status === "active"; }).map(function (t) {
          var next = (t.week_tasks && t.week_tasks[0]) || null;
          return {
            emoji:     t.emoji,
            name_hi:   t.name_hi,
            day:       t.day_number,
            stage_hi:  t.current_stage ? t.current_stage.name_hi : "",
            next_task: next ? next.title_hi : "",
            next_date: next ? next.date : ""
          };
        }));
      })
      .catch(function () {});
  }

  function renderSuggestions() {
    var list = document.getElementById("km-book-tab-suggest");
    if (!list) return;
    if (state.suggestLoaded) return; // build once per open
    state.suggestLoaded = true;

    list.innerHTML = '<div class="km-book-loading"><span class="km-book-spinner">↻</span> आपके लिए सुझाव बन रहे हैं...</div>';

    whenProfile(function (profile) {
      var el = document.getElementById("km-book-tab-suggest");
      if (!el) return;
      var html = "";
      var crops = farmerCrops(profile);

      if (!getToken()) {
        html += '<div class="km-book-card warn">' +
          '<div class="km-book-product">🔑 लॉगिन करें — निजी सुझाव पाएं</div>' +
          '<div class="km-book-line">प्रोफ़ाइल में अपनी फसल और जिला भरें, तो यहाँ आपके लिए मंडी भाव और मौसम के सुझाव दिखेंगे।</div>' +
          '<button class="km-book-ghost-btn" data-href="' + loginUrl() + '" style="margin-top:8px">लॉगिन / साइनअप करें</button>' +
        '</div>';
      } else if (!crops.length || !(profile && profile.district)) {
        html += '<div class="km-book-card warn">' +
          '<div class="km-book-product">📝 प्रोफ़ाइल पूरी करें</div>' +
          '<div class="km-book-line">अपनी फसल और जिला भरें — उसी हिसाब से भाव और मौसम के सुझाव यहाँ दिखेंगे।</div>' +
          '<button class="km-book-ghost-btn" data-href="' + profileUrl() + '" style="margin-top:8px">प्रोफ़ाइल खोलें</button>' +
        '</div>';
      }

      // मेरी फसल calendar cards (filled async from localStorage/API)
      html += '<div id="km-book-fasal-slot"></div>';

      // Generic quick links always useful.
      // नेट भाव goes first: it renders directly beneath the farmer's own crop
      // prices above, which is the moment the "ऊँचा रेट = ज़्यादा पैसा?" doubt
      // is live. Absolute href — the book opens on article pages a directory
      // down, where pagePrefix()-style relative links would not reach /bhav.
      var generic =
        suggestLinkCard("🚜", "नेट भाव — भाड़ा घटाकर देखें", "ऊँचा रेट देने वाली दूर की मंडी भाड़े के बाद कम दे सकती है। आस-पास की मंडियों का असली नेट भाव देखिए।", "/bhav/net-price") +
        suggestLinkCard("🌱", "मेरी फसल कैलेंडर", "बुवाई की तारीख डालें — सिंचाई, खाद और कीट-निगरानी की याद हर हफ्ते यहीं मिलेगी।", fasalUrl()) +
        suggestLinkCard("🛒", "अपनी फसल बेचें", "Krashi Bazar पर फोटो के साथ पोस्ट करें — खरीदार सीधे संपर्क करेंगे।", bazarUrl()) +
        suggestLinkCard("🏛️", "सरकारी योजनाएं", "PM-Kisan, फसल बीमा और अन्य योजनाओं की जानकारी देखें।", pagePrefix() + "sarkari_yojana.html");

      if (!crops.length) {
        el.innerHTML = html + generic;
        wireActions(el);
        loadFasalCards();
        return;
      }

      // Personalized: mandi prices for the farmer's crops
      fetch(apiBase() + "/shop/commodities")
        .then(function (r) { return r.json(); })
        .then(function (res) { return (res && res.commodities) || []; })
        .catch(function () { return []; })
        .then(function (avail) {
          var pending = crops.length;
          var cards = new Array(crops.length);
          crops.forEach(function (crop, i) {
            fetchMandiFor(crop, avail, profile, function (row) {
              cards[i] = row ? mandiPriceCard(crop, row) : "";
              pending--;
              if (pending === 0) {
                var el2 = document.getElementById("km-book-tab-suggest");
                if (!el2) return;
                var priceHtml = cards.join("");
                if (priceHtml) priceHtml = '<div class="km-book-section-title">📊 आपकी फसलों के आज के भाव</div>' + priceHtml;
                el2.innerHTML = html + priceHtml + generic;
                wireActions(el2);
                loadFasalCards();
              }
            });
          });
        });
    });
  }

  // ── Profile loading (shared across tabs) ──────────────────
  var profileWaiters = [];
  function whenProfile(cb) {
    if (state.profileDone) { cb(state.profile); return; }
    profileWaiters.push(cb);
  }
  function loadProfile() {
    state.profileDone = false;
    fetchProfile(function (profile) {
      state.profile = profile;
      state.profileDone = true;
      profileWaiters.splice(0).forEach(function (cb) { cb(profile); });
      renderHistory(); // identity strip appears once profile lands
    });
  }

  // ── Common actions ────────────────────────────────────────
  function wireActions(root) {
    root.querySelectorAll("[data-accept]").forEach(function (btn) {
      if (btn._kmWired) return; btn._kmWired = true;
      btn.addEventListener("click", function () { acceptQuote(btn.getAttribute("data-accept")); });
    });
    root.querySelectorAll("[data-href]").forEach(function (elm) {
      if (elm._kmWired) return; elm._kmWired = true;
      elm.addEventListener("click", function () { window.location.href = elm.getAttribute("data-href"); });
    });
  }

  function acceptQuote(tc) {
    fetchOrderHistory(function (orders) {
      var o = orders.find(function (x) { return x.tracking_code === tc; }) || {};
      var total = Number(o.quote_total || 0).toLocaleString("en-IN");
      var msg = "✅ *प्री-बुक पक्की करनी है*\n" +
        "🆔 " + tc + "\n" +
        "📦 " + productLabel(o) + "\n" +
        "💰 दाम: ₹" + total + "\n" +
        "मैं यह ऑर्डर आगे बढ़ाना चाहता हूँ।";
      window.open("https://wa.me/" + WA_NUMBER + "?text=" + encodeURIComponent(msg), "_blank");
    });
  }

  // ── Tabs ──────────────────────────────────────────────────
  function switchTab(name) {
    ["alerts", "history", "suggest"].forEach(function (t) {
      var pane = document.getElementById("km-book-tab-" + t);
      var btn = document.querySelector('.km-book-tab-btn[data-tab="' + t + '"]');
      if (pane) pane.style.display = (t === name) ? "" : "none";
      if (btn) btn.classList.toggle("active", t === name);
    });
    if (name === "suggest") renderSuggestions();
  }

  // ── Open/close + badge ────────────────────────────────────
  function openBook() {
    var overlay = document.getElementById("km-book-modal");
    if (!overlay) return;
    overlay.classList.add("open");
    state = { orders: null, profile: null, profileDone: false, suggestLoaded: false };
    switchTab("alerts");
    var loading = '<div class="km-book-loading"><span class="km-book-spinner">↻</span> लोड हो रहा है...</div>';
    document.getElementById("km-book-tab-alerts").innerHTML = loading;
    document.getElementById("km-book-tab-history").innerHTML = loading;
    document.getElementById("km-book-tab-suggest").innerHTML = "";
    loadProfile();
    fetchOrderHistory(function (orders) {
      state.orders = orders;
      renderAlerts();
      renderHistory();
      markAllSeen(orders);
      var badge = document.getElementById("km-book-badge");
      if (badge) badge.style.display = "none";
    });
  }
  function closeBook() {
    var overlay = document.getElementById("km-book-modal");
    if (overlay) overlay.classList.remove("open");
  }
  // Crops with a task due *today* (now_count) — lets the 📒 badge nag the farmer
  // to open KrashiBook even when there are no order updates. 0 for guests.
  function fetchCropNowCount(cb) {
    var token = getToken();
    if (!token) { cb(0); return; }
    fetch(apiBase() + "/crop-calendar/nudges", { headers: { "Authorization": "Bearer " + token } })
      .then(function (r) { return r.json(); })
      .then(function (res) { cb((res && res.success && res.data && res.data.now_count) || 0); })
      .catch(function () { cb(0); });
  }
  // A lapsed or lapsing listing (/dukan/product). Same contract as the crop
  // count — the point of the badge is that the dealer does NOT have to open
  // KrashiBook to find out his listing is about to go dark. 0 for farmers,
  // who own no listing, and 0 for guests.
  function fetchDukanNowCount(cb) {
    var token = getToken();
    if (!token) { cb(0); return; }
    fetch(apiBase() + "/dukan/subscription", { headers: { "Authorization": "Bearer " + token } })
      .then(function (r) { return r.json(); })
      .then(function (res) { cb((res && res.success && res.data && res.data.now_count) || 0); })
      .catch(function () { cb(0); });
  }
  function updateBadge() {
    var badge = document.getElementById("km-book-badge");
    if (!badge) return;
    fetchOrderHistory(function (orders) {
      var seen = seenMap();
      var fresh = orders.filter(function (o) { return seen[o.tracking_code] !== lc(o); });
      fetchCropNowCount(function (nowCount) {
        fetchDukanNowCount(function (dukanCount) {
          var total = fresh.length + nowCount + dukanCount;
          if (total) { badge.textContent = total; badge.style.display = ""; }
          else { badge.style.display = "none"; }
        });
      });
    });
  }

  // ── Injection ─────────────────────────────────────────────
  var CSS =
    // Book button (mirrors shop.html .header-bell-btn)
    ".km-book-btn{position:relative;background:#f1f5f9;border:1px solid #cbd5e0;border-radius:50%;width:34px;height:34px;font-size:16px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;transition:transform .15s,background .15s;flex-shrink:0;padding:0;line-height:1;}" +
    ".km-book-btn:hover{transform:scale(1.05);background:#e8eef3;}" +
    ".km-book-btn.km-book-float{position:fixed;top:14px;right:14px;width:44px;height:44px;font-size:20px;background:#fff;box-shadow:0 4px 16px rgba(0,0,0,.18);z-index:9998;}" +
    ".km-book-badge{position:absolute;top:-4px;right:-4px;min-width:17px;height:17px;padding:0 4px;background:#e53935;color:#fff;border-radius:9px;font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;line-height:1;box-shadow:0 0 0 2px #fff;}" +
    // Modal
    ".km-book-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.52);backdrop-filter:blur(4px);z-index:3200;align-items:flex-start;justify-content:center;padding:70px 16px 16px;}" +
    ".km-book-overlay.open{display:flex;}" +
    ".km-book-box{background:#fff;border-radius:18px;width:100%;max-width:480px;max-height:84vh;overflow-y:auto;padding:20px 18px 16px;box-shadow:0 24px 64px rgba(0,0,0,0.28);position:relative;font-family:'DM Sans','Noto Sans Devanagari',sans-serif;}" +
    ".km-book-title{font-size:17px;font-weight:800;color:#1b5e20;margin-bottom:4px;display:flex;align-items:center;gap:8px;}" +
    ".km-book-subtitle{font-size:12px;color:#8a958f;margin-bottom:12px;}" +
    ".km-book-close{position:absolute;top:12px;right:12px;background:#f0f2f5;border:none;border-radius:50%;width:30px;height:30px;cursor:pointer;font-size:15px;color:#555;}" +
    ".km-book-refresh-btn{position:absolute;top:12px;right:48px;background:#f0f2f5;border:none;border-radius:12px;padding:0 12px;height:30px;cursor:pointer;font-size:12px;font-weight:700;color:#2d6a4f;display:flex;align-items:center;justify-content:center;transition:all .2s ease;font-family:inherit;}" +
    ".km-book-refresh-btn:hover{background:#e1e5eb;}" +
    // Tabs
    ".km-book-tabs{display:flex;gap:6px;margin-bottom:12px;position:sticky;top:-20px;background:#fff;padding:6px 0;z-index:2;}" +
    ".km-book-tab-btn{flex:1;background:#eef2ef;border:none;border-radius:12px;padding:9px 4px;font-size:12.5px;font-weight:800;color:#2d6a4f;cursor:pointer;font-family:inherit;white-space:nowrap;}" +
    ".km-book-tab-btn.active{background:#2d6a4f;color:#fff;}" +
    // Cards (shared look with old bell)
    ".km-book-card{border:1px solid #e6ebe8;border-radius:14px;padding:12px 13px;margin-bottom:10px;}" +
    ".km-book-card.quoted{border-color:#2d6a4f;background:#f2faf5;box-shadow:0 2px 10px rgba(45,106,79,0.08);}" +
    ".km-book-card.warn{border-color:#f0c36d;background:#fffaf0;}" +
    ".km-book-linkcard{cursor:pointer;transition:box-shadow .15s;}" +
    ".km-book-linkcard:hover{box-shadow:0 3px 12px rgba(0,0,0,0.09);}" +
    ".km-book-card-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;}" +
    ".km-book-tracking{font-size:11px;font-weight:700;color:#8a958f;font-family:monospace;}" +
    ".km-book-chip{font-size:11px;font-weight:800;padding:3px 9px;border-radius:20px;white-space:nowrap;}" +
    ".km-book-chip.quoted{background:#2d6a4f;color:#fff;}" +
    ".km-book-chip.pending{background:#fff3e0;color:#e65100;}" +
    ".km-book-chip.ok{background:#e8f5e9;color:#1b5e20;}" +
    ".km-book-chip.cancel{background:#fdecea;color:#c62828;}" +
    ".km-book-chip.warnchip{background:#fff3e0;color:#b26a00;}" +
    ".km-book-new-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#e53935;margin-right:5px;vertical-align:middle;}" +
    ".km-book-product{font-size:14px;font-weight:700;color:#1c2b22;margin-bottom:2px;}" +
    ".km-book-quote-total{font-size:20px;font-weight:800;color:#1b5e20;margin:6px 0;}" +
    ".km-book-line{font-size:12.5px;color:#425a4e;margin:2px 0;}" +
    ".km-book-chg{font-size:12px;font-weight:800;}" +
    ".km-book-chg.up{color:#1b5e20;}" +
    ".km-book-chg.down{color:#c62828;}" +
    ".km-book-accept-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;width:100%;margin-top:10px;background:#25D366;color:#fff;border:none;border-radius:12px;padding:11px;font-size:14px;font-weight:800;cursor:pointer;font-family:inherit;}" +
    ".km-book-accept-btn:active{transform:scale(0.98);}" +
    ".km-book-ghost-btn{width:100%;margin-top:4px;background:#eef2ef;border:none;border-radius:12px;padding:11px;font-size:13px;font-weight:700;color:#2d6a4f;cursor:pointer;font-family:inherit;}" +
    ".km-book-section-title{font-size:13px;font-weight:800;color:#1b5e20;margin:4px 0 8px;}" +
    // History ledger
    ".km-book-idcard{background:#f2faf5;border:1px solid #d9e8de;border-radius:14px;padding:11px 13px;margin-bottom:10px;}" +
    ".km-book-idcard-who{font-size:13.5px;font-weight:800;color:#1b5e20;}" +
    ".km-book-idcard-stats{font-size:12px;color:#557a63;margin-top:3px;}" +
    ".km-book-ledger{border:1px solid #e6ebe8;border-radius:14px;overflow:hidden;margin-bottom:10px;}" +
    ".km-book-ledger-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 13px;border-bottom:1px solid #eef2ef;}" +
    ".km-book-ledger-row:last-child{border-bottom:none;}" +
    ".km-book-ledger-main{min-width:0;}" +
    ".km-book-ledger-side{display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex-shrink:0;}" +
    ".km-book-ledger-amt{font-size:14px;font-weight:800;color:#1b5e20;}" +
    ".km-book-ledger-amt.muted{color:#b9c4be;font-weight:600;}" +
    // Misc
    ".km-book-empty{text-align:center;padding:34px 12px;color:#8a958f;line-height:1.6;}" +
    ".km-book-empty .emoji{font-size:40px;display:block;margin-bottom:10px;}" +
    ".km-book-loading{text-align:center;padding:24px;color:#999;font-size:13px;display:flex;align-items:center;justify-content:center;gap:8px;}" +
    ".km-book-spinner{display:inline-block;animation:km-book-spin 1s linear infinite;}" +
    "@keyframes km-book-spin{to{transform:rotate(360deg);}}";

  function injectStyles() {
    var style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function buildButton() {
    var btn = document.createElement("button");
    btn.className = "km-book-btn";
    btn.id = "km-book-btn";
    btn.type = "button";
    btn.title = "KrashiBook — मेरी किताब: सूचनाएं, इतिहास व सुझाव";
    btn.setAttribute("aria-label", "KrashiBook");
    btn.innerHTML = '📒<span class="km-book-badge" id="km-book-badge" style="display:none">0</span>';
    btn.addEventListener("click", openBook);
    return btn;
  }

  function placeButton(btn) {
    // Prefer sitting just left of the header avatar (matches shop.html).
    var avatar = document.getElementById("header-avatar-btn") ||
      document.querySelector(".header-avatar-btn, .avatar-btn");
    if (avatar && avatar.parentNode) {
      avatar.parentNode.insertBefore(btn, avatar);
      return;
    }
    // No header avatar on this page → float it top-right.
    btn.classList.add("km-book-float");
    document.body.appendChild(btn);
  }

  function buildModal() {
    var overlay = document.createElement("div");
    overlay.className = "km-book-overlay";
    overlay.id = "km-book-modal";
    overlay.innerHTML =
      '<div class="km-book-box">' +
        '<button class="km-book-close" type="button" aria-label="Close">✕</button>' +
        '<button class="km-book-refresh-btn" type="button" title="रीफ़्रेश करें / Refresh" aria-label="Refresh">↻ Refresh</button>' +
        '<div class="km-book-title">📒 KrashiBook</div>' +
        '<div class="km-book-subtitle">आपकी किताब — सूचनाएं, ऑर्डर इतिहास और आपके लिए सुझाव</div>' +
        '<div class="km-book-tabs">' +
          '<button class="km-book-tab-btn active" type="button" data-tab="alerts">🔔 सूचनाएं</button>' +
          '<button class="km-book-tab-btn" type="button" data-tab="history">📖 इतिहास</button>' +
          '<button class="km-book-tab-btn" type="button" data-tab="suggest">💡 सुझाव</button>' +
        '</div>' +
        '<div id="km-book-tab-alerts"></div>' +
        '<div id="km-book-tab-history" style="display:none"></div>' +
        '<div id="km-book-tab-suggest" style="display:none"></div>' +
      '</div>';
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeBook(); });
    overlay.querySelector(".km-book-close").addEventListener("click", closeBook);
    overlay.querySelector(".km-book-refresh-btn").addEventListener("click", openBook);
    overlay.querySelectorAll(".km-book-tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { switchTab(btn.getAttribute("data-tab")); });
    });
    document.body.appendChild(overlay);
  }

  ready(function () {
    // Never double up on shop.html's native bell, or on a page that already has the book.
    if (document.getElementById("header-bell-btn") || document.getElementById("km-book-btn")) return;
    injectStyles();
    placeButton(buildButton());
    buildModal();
    updateBadge();
  });
})();
