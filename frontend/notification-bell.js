// ============================================================
// KrashiMitra — Universal notification bell (🔔)
// ------------------------------------------------------------
// Drops the shop.html order/quote bell onto every page with no
// markup changes. Self-contained: injects its own CSS, the bell
// button, and the notifications modal, then wires up all logic.
//
// Placement: inserted just before the header avatar button when
// one exists (matching shop.html's header look); otherwise it
// falls back to a floating top-right button.
//
// Identity + data are shared with shop.html via the same
// localStorage keys (km_session_id, krishi_token, km_seen_status)
// and the /order/history API, so the badge + list stay in sync
// no matter which page the farmer is on.
//
// Usage: include once per page, e.g.
//   <script src="notification-bell.js"></script>
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
    return window.KRASHIMITRA_API_BASE || "https://krashi-mitra-v1.onrender.com";
  }
  // Location-aware path to shop.html (pages under /articles/ need to go up one level).
  function shopUrl() {
    var prefix = location.pathname.indexOf("/articles/") !== -1 ? "../" : "";
    return prefix + "shop.html?orders=1";
  }

  // ── Identity + data (mirrors shop.html) ───────────────────
  function getSessionId() {
    var sid = localStorage.getItem("km_session_id");
    if (!sid) {
      sid = "km_" + Math.random().toString(36).substr(2, 8);
      localStorage.setItem("km_session_id", sid);
    }
    return sid;
  }

  function fetchOrderHistory(cb) {
    var token = localStorage.getItem("krishi_token");
    var headers = {};
    var url;
    if (token && token !== "null" && token !== "undefined") {
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

  // ── Helpers ───────────────────────────────────────────────
  function clean(s) { return String(s == null ? "" : s).replace(/[<>]/g, ""); }
  function lc(o) { return String(o.status || "").toLowerCase(); }
  function isQuoted(o) {
    return o.quote_total != null || String(o.status || "").toLowerCase() === "quoted";
  }

  var NOTIF_ALIAS = { prebook: "pending", verified: "quoted", canceled: "cancelled" };
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
  function dot(isNew) { return isNew ? '<span class="km-notif-new-dot"></span>' : ""; }
  function when(o) {
    if (!o.created_at) return "";
    try { return new Date(o.created_at).toLocaleDateString("hi-IN", { day: "numeric", month: "short" }); }
    catch (e) { return ""; }
  }

  // ── Rendering ─────────────────────────────────────────────
  function quoteCard(o, isNew) {
    var total = Number(o.quote_total || 0).toLocaleString("en-IN");
    return '<div class="km-notif-card quoted">' +
      '<div class="km-notif-card-head">' +
        '<span class="km-notif-tracking">' + dot(isNew) + clean(o.tracking_code) + '</span>' +
        '<span class="km-notif-chip quoted">💰 दाम तैयार</span>' +
      '</div>' +
      '<div class="km-notif-product">' + clean(o.product_name) + ' · ' + (o.quantity || 1) + '</div>' +
      '<div class="km-notif-quote-total">पूरा दाम: ₹' + total + '</div>' +
      (o.delivery_info ? '<div class="km-notif-line">🚚 ' + clean(o.delivery_info) + '</div>' : "") +
      (o.quote_note ? '<div class="km-notif-line">📝 ' + clean(o.quote_note) + '</div>' : "") +
      '<button class="km-notif-accept-btn" data-accept="' + clean(o.tracking_code) + '">' +
        '<img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" alt="WA" style="width:17px;height:17px;flex-shrink:0"> WhatsApp पर पक्का करें' +
      '</button>' +
    '</div>';
  }
  function statusCard(o, isNew) {
    var meta = STATUS_NOTIF[stageKey(o)] || { chip: clean(o.status || "अपडेट"), cls: "pending", msg: function () { return ""; } };
    var w = when(o);
    return '<div class="km-notif-card">' +
      '<div class="km-notif-card-head">' +
        '<span class="km-notif-tracking">' + dot(isNew) + clean(o.tracking_code) + '</span>' +
        '<span class="km-notif-chip ' + meta.cls + '">' + meta.chip + '</span>' +
      '</div>' +
      '<div class="km-notif-product">' + clean(o.product_name) + ' · ' + (o.quantity || 1) + '</div>' +
      '<div class="km-notif-line">' + meta.msg(o) + '</div>' +
      (w ? '<div class="km-notif-line" style="opacity:.6;font-size:11px;">📅 ' + w + '</div>' : "") +
    '</div>';
  }

  function renderNotifs(orders, list) {
    if (!orders.length) {
      list.innerHTML = '<div class="km-notif-empty"><span class="emoji">🔕</span>' +
        'अभी कोई सूचना नहीं।<br><span style="font-size:12px">प्री-बुक करें — हर अपडेट यहाँ दिखेगा।</span></div>' +
        '<button class="km-notif-allorders-btn" data-allorders="1">📋 सभी ऑर्डर देखें</button>';
      wireListActions(list);
      return;
    }
    var sorted = orders.slice().sort(function (a, b) {
      var qa = isQuoted(a) ? 1 : 0, qb = isQuoted(b) ? 1 : 0;
      if (qa !== qb) return qb - qa;
      return new Date(b.created_at || 0) - new Date(a.created_at || 0);
    });
    var seen = seenMap();
    var html = "";
    sorted.forEach(function (o) {
      var isNew = seen[o.tracking_code] !== lc(o);
      html += isQuoted(o) ? quoteCard(o, isNew) : statusCard(o, isNew);
    });
    html += '<button class="km-notif-allorders-btn" data-allorders="1">📋 सभी ऑर्डर देखें</button>';
    list.innerHTML = html;
    wireListActions(list);
  }

  function wireListActions(list) {
    list.querySelectorAll("[data-accept]").forEach(function (btn) {
      btn.addEventListener("click", function () { acceptQuote(btn.getAttribute("data-accept")); });
    });
    list.querySelectorAll("[data-allorders]").forEach(function (btn) {
      // The full orders modal lives on shop.html.
      btn.addEventListener("click", function () { window.location.href = shopUrl(); });
    });
  }

  function acceptQuote(tc) {
    fetchOrderHistory(function (orders) {
      var o = orders.find(function (x) { return x.tracking_code === tc; }) || {};
      var total = Number(o.quote_total || 0).toLocaleString("en-IN");
      var msg = "✅ *प्री-बुक पक्की करनी है*\n" +
        "🆔 " + tc + "\n" +
        "📦 " + (o.product_name || "") + " · " + (o.quantity || 1) + "\n" +
        "💰 दाम: ₹" + total + "\n" +
        "मैं यह ऑर्डर आगे बढ़ाना चाहता हूँ।";
      window.open("https://wa.me/" + WA_NUMBER + "?text=" + encodeURIComponent(msg), "_blank");
    });
  }

  // ── Modal open/close + badge ──────────────────────────────
  function openNotifications() {
    var overlay = document.getElementById("km-notif-modal");
    if (!overlay) return;
    overlay.classList.add("open");
    var list = document.getElementById("km-notif-list");
    list.innerHTML = '<div class="km-notif-loading"><span class="km-notif-spinner">↻</span> लोड हो रहा है...</div>';
    fetchOrderHistory(function (orders) {
      renderNotifs(orders, list);
      markAllSeen(orders);
      var badge = document.getElementById("km-bell-badge");
      if (badge) badge.style.display = "none";
    });
  }
  function closeNotifModal() {
    var overlay = document.getElementById("km-notif-modal");
    if (overlay) overlay.classList.remove("open");
  }
  function updateBellBadge() {
    var badge = document.getElementById("km-bell-badge");
    if (!badge) return;
    fetchOrderHistory(function (orders) {
      var seen = seenMap();
      var fresh = orders.filter(function (o) { return seen[o.tracking_code] !== lc(o); });
      if (fresh.length) { badge.textContent = fresh.length; badge.style.display = ""; }
      else { badge.style.display = "none"; }
    });
  }

  // ── Injection ─────────────────────────────────────────────
  var CSS =
    // Bell button (mirrors shop.html .header-bell-btn)
    ".km-bell-btn{position:relative;background:#f1f5f9;border:1px solid #cbd5e0;border-radius:50%;width:34px;height:34px;font-size:16px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;transition:transform .15s,background .15s;flex-shrink:0;padding:0;line-height:1;}" +
    ".km-bell-btn:hover{transform:scale(1.05);background:#e8eef3;}" +
    ".km-bell-btn.km-bell-float{position:fixed;top:14px;right:14px;width:44px;height:44px;font-size:20px;background:#fff;box-shadow:0 4px 16px rgba(0,0,0,.18);z-index:9998;}" +
    ".km-bell-badge{position:absolute;top:-4px;right:-4px;min-width:17px;height:17px;padding:0 4px;background:#e53935;color:#fff;border-radius:9px;font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;line-height:1;box-shadow:0 0 0 2px #fff;}" +
    // Modal
    ".km-notif-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.52);backdrop-filter:blur(4px);z-index:3200;align-items:flex-start;justify-content:center;padding:70px 16px 16px;}" +
    ".km-notif-overlay.open{display:flex;}" +
    ".km-notif-box{background:#fff;border-radius:18px;width:100%;max-width:460px;max-height:82vh;overflow-y:auto;padding:20px 18px 16px;box-shadow:0 24px 64px rgba(0,0,0,0.28);position:relative;font-family:'DM Sans','Noto Sans Devanagari',sans-serif;}" +
    ".km-notif-title{font-size:17px;font-weight:800;color:#1b5e20;margin-bottom:14px;display:flex;align-items:center;gap:8px;}" +
    ".km-notif-close{position:absolute;top:12px;right:12px;background:#f0f2f5;border:none;border-radius:50%;width:30px;height:30px;cursor:pointer;font-size:15px;color:#555;}" +
    ".km-notif-card{border:1px solid #e6ebe8;border-radius:14px;padding:12px 13px;margin-bottom:10px;}" +
    ".km-notif-card.quoted{border-color:#2d6a4f;background:#f2faf5;box-shadow:0 2px 10px rgba(45,106,79,0.08);}" +
    ".km-notif-card-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;}" +
    ".km-notif-tracking{font-size:11px;font-weight:700;color:#8a958f;font-family:monospace;}" +
    ".km-notif-chip{font-size:11px;font-weight:800;padding:3px 9px;border-radius:20px;white-space:nowrap;}" +
    ".km-notif-chip.quoted{background:#2d6a4f;color:#fff;}" +
    ".km-notif-chip.pending{background:#fff3e0;color:#e65100;}" +
    ".km-notif-chip.ok{background:#e8f5e9;color:#1b5e20;}" +
    ".km-notif-chip.cancel{background:#fdecea;color:#c62828;}" +
    ".km-notif-new-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#e53935;margin-right:5px;vertical-align:middle;}" +
    ".km-notif-product{font-size:14px;font-weight:700;color:#1c2b22;margin-bottom:2px;}" +
    ".km-notif-quote-total{font-size:20px;font-weight:800;color:#1b5e20;margin:6px 0;}" +
    ".km-notif-line{font-size:12.5px;color:#425a4e;margin:2px 0;}" +
    ".km-notif-accept-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;width:100%;margin-top:10px;background:#25D366;color:#fff;border:none;border-radius:12px;padding:11px;font-size:14px;font-weight:800;cursor:pointer;font-family:inherit;}" +
    ".km-notif-accept-btn:active{transform:scale(0.98);}" +
    ".km-notif-allorders-btn{width:100%;margin-top:4px;background:#eef2ef;border:none;border-radius:12px;padding:11px;font-size:13px;font-weight:700;color:#2d6a4f;cursor:pointer;font-family:inherit;}" +
    ".km-notif-empty{text-align:center;padding:34px 12px;color:#8a958f;line-height:1.6;}" +
    ".km-notif-empty .emoji{font-size:40px;display:block;margin-bottom:10px;}" +
    ".km-notif-refresh-btn{position:absolute;top:12px;right:48px;background:#f0f2f5;border:none;border-radius:12px;padding:0 12px;height:30px;cursor:pointer;font-size:12px;font-weight:700;color:#2d6a4f;display:flex;align-items:center;justify-content:center;transition:all .2s ease;font-family:inherit;}" +
    ".km-notif-refresh-btn:hover{background:#e1e5eb;}" +
    ".km-notif-loading{text-align:center;padding:24px;color:#999;font-size:13px;display:flex;align-items:center;justify-content:center;gap:8px;}" +
    ".km-notif-spinner{display:inline-block;animation:km-notif-spin 1s linear infinite;}" +
    "@keyframes km-notif-spin{to{transform:rotate(360deg);}}";

  function injectStyles() {
    var style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function buildBell() {
    var btn = document.createElement("button");
    btn.className = "km-bell-btn";
    btn.id = "km-bell-btn";
    btn.type = "button";
    btn.title = "मेरी प्री-बुक व सूचनाएं";
    btn.setAttribute("aria-label", "Notifications");
    btn.innerHTML = '🔔<span class="km-bell-badge" id="km-bell-badge" style="display:none">0</span>';
    btn.addEventListener("click", openNotifications);
    return btn;
  }

  function placeBell(btn) {
    // Prefer sitting just left of the header avatar (matches shop.html).
    var avatar = document.getElementById("header-avatar-btn") ||
      document.querySelector(".header-avatar-btn, .avatar-btn");
    if (avatar && avatar.parentNode) {
      avatar.parentNode.insertBefore(btn, avatar);
      return;
    }
    // No header avatar on this page → float it top-right.
    btn.classList.add("km-bell-float");
    document.body.appendChild(btn);
  }

  function buildModal() {
    var overlay = document.createElement("div");
    overlay.className = "km-notif-overlay";
    overlay.id = "km-notif-modal";
    overlay.innerHTML =
      '<div class="km-notif-box">' +
        '<button class="km-notif-close" type="button" aria-label="Close">✕</button>' +
        '<button class="km-notif-refresh-btn" type="button" title="रीफ़्रेश करें / Refresh" aria-label="Refresh">↻ Refresh</button>' +
        '<div class="km-notif-title">🔔 सूचनाएं व मेरी प्री-बुक</div>' +
        '<div id="km-notif-list"><div class="km-notif-loading"><span class="km-notif-spinner">↻</span> लोड हो रहा है...</div></div>' +
      '</div>';
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeNotifModal(); });
    overlay.querySelector(".km-notif-close").addEventListener("click", closeNotifModal);
    overlay.querySelector(".km-notif-refresh-btn").addEventListener("click", openNotifications);
    document.body.appendChild(overlay);
  }

  ready(function () {
    // Never double up on shop.html's native bell.
    if (document.getElementById("header-bell-btn") || document.getElementById("km-bell-btn")) return;
    injectStyles();
    placeBell(buildBell());
    buildModal();
    updateBellBadge();
  });
})();
