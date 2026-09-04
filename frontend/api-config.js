// ============================================================
// KrashiMitra — Frontend API base auto-detection

// ============================================================
(function () {
  if (window.KRASHIMITRA_API_BASE) return; // respect a manual override

  var host = location.hostname;
  var isLocal =
    host === 'localhost' ||
    host === '127.0.0.1' ||
    host === '' ||                 // file://
    /^192\.168\./.test(host) ||    // common LAN ranges
    /^10\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host);

  var defaultPort = '8000';
  if (location.port && location.port !== '5500' && location.port !== '3000' && location.port !== '5173' && location.port !== '8080') {
    defaultPort = location.port;
  }
  // Production is served two ways: krashimitra.in (Netlify static + a handful
  // of proxied paths in _redirects — bhav/product/share/alerts/sitemap/llms
  // ONLY) and the Render host below (the FastAPI app serving its own
  // frontend, same origin as the API). `location.origin` would be right on
  // the Render domain but silently 404s everything else (login, signup,
  // /auth/*, /profile, ...) on krashimitra.in since Netlify doesn't proxy
  // those paths. Always hitting the Render URL directly works on both —
  // it's a cross-origin call from krashimitra.in, but that origin is already
  // in the backend's CORS allowlist.
  //
  // ⚠️ DO NOT EDIT THE URL BELOW BY HAND. Render reassigns this subdomain
  // every time the service is recreated (twice so far, each an outage). The
  // value is owned by config/backend-origin.txt and written here by
  //     python tools/set_backend_origin.py <new-url>
  // which updates _redirects and every other page in the same pass. This file
  // cannot read the config at request time — it must set the API base
  // synchronously, before any page script runs, so it cannot await a fetch.
  window.KRASHIMITRA_API_BASE = isLocal
    ? location.protocol + '//' + (host || 'localhost') + ':' + defaultPort
    : 'https://krashi-mitra-v1-mrp4.onrender.com';
  window.KRASHIMITRA_IS_LOCAL = isLocal;

  console.log('[KrashiMitra] API base =', window.KRASHIMITRA_API_BASE);
})();

// ── Google OAuth Client ID ────────────────────────────────────
window.KRASHIMITRA_GOOGLE_CLIENT_ID = "235912622385-faavoh67rvg0m126bj5af8ot3n2k0shd.apps.googleusercontent.com";

// ── 🔒 Login gate ─────────────────────────────────────────────
// Ordering and 🔔 भाव अलर्ट both need an account. Both servers enforce that
// (401), so this is the courtesy explanation, not the lock.
//
// Self-contained on purpose — styles are injected at call time rather than
// living in a stylesheet. The two pages that need this gate have completely
// separate CSS: /bhav is server-rendered with its palette inlined by bhav.py,
// shop.html carries its own. A shared class would have to be added to both and
// kept in sync; a script every page already loads cannot drift.
(function () {
  var STYLE_ID = "km-gate-style";
  var CSS = [
    '.km-gate{position:fixed;inset:0;z-index:99999;display:none;align-items:center;',
      'justify-content:center;padding:20px;background:rgba(26,46,35,.55);',
      '-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}',
    '.km-gate.open{display:flex}',
    '.km-gate-card{background:#fff;border-radius:18px;max-width:360px;width:100%;',
      'padding:26px 22px 22px;text-align:center;position:relative;',
      "font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',sans-serif;",
      'box-shadow:0 18px 50px rgba(26,60,46,.28);animation:km-gate-in .18s ease-out}',
    '@keyframes km-gate-in{from{opacity:0;transform:translateY(10px) scale(.97)}}',
    '.km-gate-x{position:absolute;top:10px;right:12px;background:none;border:none;',
      'font-size:19px;line-height:1;color:#7c8983;cursor:pointer;padding:6px}',
    '.km-gate-emoji{font-size:42px;line-height:1;margin-bottom:10px}',
    '.km-gate-title{font-size:17px;font-weight:800;color:#1a2e23;margin-bottom:7px}',
    '.km-gate-text{font-size:13.5px;font-weight:500;color:#4a5a52;line-height:1.65;margin-bottom:18px}',
    '.km-gate-cta{display:block;background:#2d6a4f;color:#fff;text-decoration:none;',
      'font-size:15px;font-weight:700;padding:13px;border-radius:11px;',
      'box-shadow:0 4px 14px rgba(45,106,79,.3)}',
    '.km-gate-cta:hover{background:#1a3c2e}',
    '.km-gate-later{display:block;width:100%;background:none;border:none;margin-top:10px;',
      'font:inherit;font-size:13px;font-weight:600;color:#7c8983;cursor:pointer;padding:7px}',
    '.km-gate-later:hover{color:#4a5a52}'
  ].join("");

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function token() {
    var t = localStorage.getItem("krishi_token");
    return (t && t !== "null" && t !== "undefined") ? t : null;
  }
  window.KMIsLoggedIn = function () { return !!token(); };

  // Where login should send the farmer back to. The whole path is kept —
  // /bhav URLs are deep (/bhav/gehu/uttar-pradesh/hardoi) and dropping the tail
  // would return him to a crop hub instead of the mandi he was looking at.
  function returnTo(resume) {
    var here = location.pathname + location.search;
    return "/login.html?next=" + encodeURIComponent(here) +
           (resume ? "&do=" + encodeURIComponent(resume) : "");
  }

  function close() {
    var el = document.getElementById("km-gate");
    if (el) el.classList.remove("open");
  }
  window.KMCloseGate = close;

  /**
   * Show the 🔒 popup. opts:
   *   title, text — what the farmer is being asked to log in for
   *   resume      — action name handed back as ?do=, so the page can finish
   *                 the job itself after login instead of making him find it again
   */
  window.KMShowLoginGate = function (opts) {
    opts = opts || {};
    ensureStyle();
    var el = document.getElementById("km-gate");
    if (!el) {
      el = document.createElement("div");
      el.id = "km-gate";
      el.className = "km-gate";
      el.innerHTML =
        '<div class="km-gate-card" role="dialog" aria-modal="true" aria-labelledby="km-gate-title">' +
          '<button class="km-gate-x" type="button" aria-label="बंद करें">✕</button>' +
          '<div class="km-gate-emoji">🔒</div>' +
          '<div class="km-gate-title" id="km-gate-title"></div>' +
          '<div class="km-gate-text"></div>' +
          '<a class="km-gate-cta" href="/login.html">लॉगिन करें</a>' +
          '<button class="km-gate-later" type="button">बाद में</button>' +
        '</div>';
      document.body.appendChild(el);
      el.addEventListener("click", function (e) { if (e.target === el) close(); });
      el.querySelector(".km-gate-x").addEventListener("click", close);
      el.querySelector(".km-gate-later").addEventListener("click", close);
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") close();
      });
    }
    el.querySelector(".km-gate-title").textContent = opts.title || "लॉगिन करें";
    el.querySelector(".km-gate-text").textContent  = opts.text  || "";
    el.querySelector(".km-gate-cta").href          = returnTo(opts.resume);
    el.classList.add("open");
  };

  /** true if the farmer may proceed; otherwise shows the popup and returns false. */
  window.KMRequireLogin = function (opts) {
    if (token()) return true;
    window.KMShowLoginGate(opts);
    return false;
  };

  /**
   * The ?do= value login handed back, consumed once. Returns "" when there is
   * nothing to resume. The parameter is stripped from the URL so a refresh or a
   * shared link doesn't fire the action a second time.
   */
  window.KMTakeResume = function () {
    var params = new URLSearchParams(location.search);
    var todo = params.get("do") || "";
    if (todo) {
      params.delete("do");
      var q = params.toString();
      history.replaceState(null, "", location.pathname + (q ? "?" + q : "") + location.hash);
    }
    return todo;
  };
})();

// ── Signing out / switching account ───────────────────────────
// localStorage holds two different kinds of thing, and they must not be treated
// alike: settings that belong to this PHONE (language, the device's location,
// the guest order handle) and data that belongs to WHOEVER IS SIGNED IN (the
// token, the header avatar, the name, the KrashiBook caches).
//
// Clearing the second kind is part of logging IN, not only of logging out. A
// farmer signing into a second account on the same phone — or a father and son
// sharing one — would otherwise keep seeing the previous account's photo, name
// and फसल summary on every page until each one happened to re-fetch, which
// looks exactly like "it logged me into the wrong account".
(function () {
  var USER_KEYS = [
    "krishi_token",       // the session itself
    "user_avatar_url",    // header avatar — painted from cache before any fetch
    "user_name",
    "km_seen_status",     // KrashiBook read-markers (that user's order/alert ids)
    "km_fasal_summary",   // मेरी फसल summary the 📒 book shows on every page
    "km_pending_order",   // a half-finished order from the previous session
    "km_login_attempts",  // login-page lockout state
    "km_cooldown_until",
    "km_cooldown_reason"
  ];
  // Deliberately kept: km_lang, km_geo, km_local_crops, km_session_id — those
  // describe the device or its guest, not the account that just left.

  /** Forget everything about the account currently signed in on this device. */
  window.KMClearUserData = function () {
    USER_KEYS.forEach(function (k) {
      try { localStorage.removeItem(k); } catch (e) {}
    });
    // Google Identity remembers the account it last signed in with and will
    // reuse it without asking — the one thing somebody switching accounts
    // definitely does not want. No-op on pages that don't load GSI.
    try {
      if (window.google && google.accounts && google.accounts.id) {
        google.accounts.id.disableAutoSelect();
      }
    } catch (e) {}
  };

  /** Clear the session and go to the login page (or `dest`). */
  window.KMLogout = function (dest) {
    window.KMClearUserData();
    window.location.href = dest || "/login.html";
  };
})();

// ── Auto Header Avatar Button Handling ─────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  const btn = document.getElementById("header-avatar-btn") || document.querySelector(".header-avatar-btn");
  if (!btn) return;
  
  if (!btn.id) btn.id = "header-avatar-btn";

  // Decide destination at CLICK time (robust to pages that hardcode the href):
  //   logged in  → /profile.html   |   logged out → /login.html (sign in)
  // Root-absolute paths, NOT bare "profile.html": the bhav/product SEO pages live
  // at nested, extensionless URLs (/bhav/wheat-atta/rajasthan/jaipur), where a
  // relative "profile.html" resolves to /bhav/wheat-atta/.../profile.html — a dead
  // page. Both files sit at the site root, so "/profile.html" is right everywhere.
  function avatarTarget() {
    const t = localStorage.getItem("krishi_token");
    return (t && t !== "null" && t !== "undefined") ? "/profile.html" : "/login.html";
  }
  btn.addEventListener("click", function (e) {
    e.preventDefault();
    window.location.href = avatarTarget();
  });

  // Renders the avatar image into `el` with a graceful fallback.
  // The image is served by the backend (Render free tier), which can be
  // cold-starting or briefly unreachable — a plain <img> would then show a
  // broken-image icon and "disappear". Instead we retry once with a cache-bust
  // after a short delay, and only then fall back to the 👤 icon.
  // Exposed on window so page-level scripts can reuse the same behaviour.
  function renderHeaderAvatar(el, src) {
    if (!el || !src) return;
    const img = document.createElement("img");
    img.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;";
    img.alt = "";
    let retried = false;
    img.onerror = function () {
      if (!retried) {
        retried = true;
        setTimeout(function () {
          img.src = src + (src.indexOf("?") === -1 ? "?" : "&") + "r=" + Date.now();
        }, 1800);
      } else {
        el.textContent = "👤";
      }
    };
    img.src = src;
    el.innerHTML = "";
    el.appendChild(img);
  }
  window.KrashiMitraRenderAvatar = renderHeaderAvatar;

  const token = localStorage.getItem("krishi_token");
  if (token) {
    // Keep href in sync for hover/middle-click/right-click UX
    btn.href = "/profile.html";

    const apiBase = window.KRASHIMITRA_API_BASE || 'https://krashi-mitra-v1-mrp4.onrender.com';
    const cachedAvatar = localStorage.getItem("user_avatar_url");
    if (cachedAvatar && cachedAvatar !== "null") {
      const src = cachedAvatar.startsWith("/") ? apiBase + cachedAvatar : cachedAvatar;
      renderHeaderAvatar(btn, src);
    }

    // Always revalidate against the server in the background, even when a
    // cached avatar was just rendered above — a stale localStorage entry
    // (e.g. an old /uploads/avatar/... path from before avatars moved into
    // Postgres) would otherwise 404 forever and never get corrected, since
    // nothing else on non-profile pages ever re-fetches /profile.
    fetch(`${apiBase}/profile`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
    .then(r => r.json())
    .catch(() => ({}))
    .then(res => {
      if (res.success && res.data) {
        if (res.data.avatar_url) {
          if (res.data.avatar_url !== cachedAvatar) {
            localStorage.setItem("user_avatar_url", res.data.avatar_url);
            const src = res.data.avatar_url.startsWith("/") ? apiBase + res.data.avatar_url : res.data.avatar_url;
            renderHeaderAvatar(btn, src);
          }
        } else if (cachedAvatar) {
          // Server has no avatar (removed / never survived the old disk
          // storage) but we had a stale cache — clear it so we stop
          // requesting a dead URL and fall back to the 👤 icon.
          localStorage.removeItem("user_avatar_url");
          btn.textContent = "👤";
        }
        if (res.data.full_name) {
          localStorage.setItem("user_name", res.data.full_name);
        }
      }
    });
  } else {
    // Lead to /login.html if not logged in
    btn.href = "/login.html";
  }
});

// ============================================================
// KrashiMitra — Dynamic Festival Wishes Pop-up Panel
// Managed via Admin Panel (/admin#festival-wishes)
// Dynamically reads /api/festival/config for image, duration, and status.
// ============================================================
(function () {
  'use strict';

  var MODAL_ID = 'km-festival-janmashtami-modal';
  var BADGE_ID = 'km-festival-reopen-badge';
  var STYLE_ID = 'km-festival-janmashtami-style';
  var DISMISS_KEY = 'km_festival_dismiss_ts';

  var _activeConfig = null;

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = [
      '#' + MODAL_ID + ' { position: fixed; inset: 0; z-index: 999999; display: flex; align-items: center; justify-content: center; padding: 14px; background: rgba(3, 10, 8, 0.76); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); opacity: 0; pointer-events: none; transition: opacity 0.32s cubic-bezier(0.16, 1, 0.3, 1); box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }',
      '#' + MODAL_ID + '.km-open { opacity: 1; pointer-events: auto; }',
      
      '.km-fest-card { position: relative; width: 100%; max-width: 410px; max-height: 92vh; overflow-y: auto; background: radial-gradient(circle at 50% 0%, #173d2f 0%, #0d221a 50%, #06110d 100%); border: 1.8px solid rgba(245, 158, 11, 0.6); border-radius: 24px; padding: 20px 18px 16px; color: #f8fafc; text-align: center; box-shadow: 0 25px 60px rgba(0,0,0,0.85), 0 0 35px rgba(245, 158, 11, 0.28), inset 0 1px 0 rgba(255,255,255,0.2); transform: scale(0.9) translateY(20px); transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1); box-sizing: border-box; scrollbar-width: thin; }',
      '#' + MODAL_ID + '.km-open .km-fest-card { transform: scale(1) translateY(0); }',
      
      '.km-fest-close { position: absolute; top: 12px; right: 12px; width: 34px; height: 34px; border-radius: 50%; background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.25); color: #e2e8f0; font-size: 18px; line-height: 1; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; z-index: 10; }',
      '.km-fest-close:hover { background: rgba(239,68,68,0.35); border-color: #ef4444; color: #fff; transform: rotate(90deg); }',

      '.km-fest-top-pill { display: inline-flex; align-items: center; gap: 6px; background: linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(16, 185, 129, 0.2)); border: 1px solid rgba(245, 158, 11, 0.5); padding: 4px 14px; border-radius: 20px; font-size: 11.5px; font-weight: 700; color: #fef08a; letter-spacing: 0.5px; margin-bottom: 12px; box-shadow: 0 2px 10px rgba(245, 158, 11, 0.2); }',
      
      '.km-fest-img-frame { position: relative; width: 100%; border-radius: 16px; overflow: hidden; border: 2px solid rgba(245, 158, 11, 0.65); box-shadow: 0 8px 25px rgba(0,0,0,0.5), 0 0 20px rgba(245, 158, 11, 0.3); margin-bottom: 14px; background: #0b1512; }',
      '.km-fest-img { width: 100%; height: auto; max-height: 230px; object-fit: cover; display: block; }',
      
      '.km-fest-title { font-size: 18.5px; font-weight: 900; line-height: 1.35; margin: 0 0 6px; background: linear-gradient(135deg, #fffbeb 0%, #fef08a 35%, #f59e0b 70%, #d97706 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-shadow: 0 2px 12px rgba(245, 158, 11, 0.3); }',
      
      '.km-fest-blessing { font-size: 12.5px; line-height: 1.55; color: #cbd5e1; margin-bottom: 13px; padding: 0 4px; }',
      
      '.km-fest-box { background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 12px; padding: 9px 12px; margin-bottom: 14px; font-size: 12px; line-height: 1.5; color: #a7f3d0; text-align: left; }',
      '.km-fest-box-item { display: flex; align-items: flex-start; gap: 7px; margin-bottom: 4px; }',
      '.km-fest-box-item:last-child { margin-bottom: 0; }',
      
      '.km-fest-btn-accept { width: 100%; background: linear-gradient(135deg, #f59e0b 0%, #d97706 50%, #b45309 100%); color: #ffffff; border: 1px solid rgba(254, 240, 138, 0.6); border-radius: 12px; padding: 11px 16px; font-size: 14px; font-weight: 800; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 4px 18px rgba(245, 158, 11, 0.45); transition: transform 0.15s, box-shadow 0.15s; }',
      '.km-fest-btn-accept:hover { transform: translateY(-1px); box-shadow: 0 6px 22px rgba(245, 158, 11, 0.65); }',
      '.km-fest-btn-accept:active { transform: translateY(1px); }',
      
      '.km-fest-btn-later { background: none; border: none; color: #94a3b8; font-size: 11.5px; font-weight: 600; margin-top: 8px; cursor: pointer; padding: 4px 10px; transition: color 0.2s; }',
      '.km-fest-btn-later:hover { color: #f1f5f9; text-decoration: underline; }',
      
      '#' + BADGE_ID + ' { position: fixed; bottom: 84px; right: 16px; z-index: 99990; display: flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #163d2f, #0d221a); border: 1.5px solid #f59e0b; border-radius: 30px; padding: 6px 13px; color: #fef08a; font-size: 11.5px; font-weight: 800; cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,0.5), 0 0 15px rgba(245,158,11,0.3); transition: transform 0.2s, box-shadow 0.2s; animation: km-fest-badge-pulse 2.4s infinite; }',
      '#' + BADGE_ID + ':hover { transform: scale(1.06); box-shadow: 0 8px 25px rgba(245,158,11,0.55); }',
      '@keyframes km-fest-badge-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.04); } }',

      // Petal confetti animation
      '.km-petal { position: fixed; pointer-events: none; z-index: 1000000; animation: km-petal-fall linear forwards; }',
      '@keyframes km-petal-fall { 0% { opacity: 1; transform: translateY(-20px) rotate(0deg) scale(1); } 100% { opacity: 0; transform: translateY(105vh) rotate(720deg) scale(0.6); } }'
    ].join('\n');
    document.head.appendChild(s);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, function (m) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m];
    });
  }

  function createModal(cfg) {
    var existing = document.getElementById(MODAL_ID);
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
    ensureStyles();

    var overlay = document.createElement('div');
    overlay.id = MODAL_ID;
    overlay.onclick = function (e) {
      if (e.target === overlay) closeModal();
    };

    var topPill = cfg.top_pill || '🪶 ॥ हरे कृष्ण ॥ 🪈';
    var imgUrl = window.KRISHNA_JANMASHTAMI_IMAGE || cfg.image_url || '/images/krishna-janmashtami.webp';
    var title = cfg.title || 'त्योहार शुभकामनाएं';
    var blessing = cfg.blessing_summary || 'कृषि मित्र परिवार की ओर से मंगलकामनाएं!';
    var b1 = cfg.bullet_1 || '';
    var b2 = cfg.bullet_2 || '';
    var cta = cfg.cta_text || '🙏 शुभकामनाएं स्वीकारें';

    var bulletsHtml = '';
    if (b1 || b2) {
      bulletsHtml = [
        '<div class="km-fest-box">',
        b1 ? '<div class="km-fest-box-item"><span>🌾</span><span>' + escapeHtml(b1) + '</span></div>' : '',
        b2 ? '<div class="km-fest-box-item"><span>🐄</span><span>' + escapeHtml(b2) + '</span></div>' : '',
        '</div>'
      ].join('');
    }

    overlay.innerHTML = [
      '<div class="km-fest-card">',
      '  <button type="button" class="km-fest-close" onclick="window.closeFestivalPopup()" title="बंद करें (Close)">✕</button>',
      '  <div class="km-fest-top-pill">' + escapeHtml(topPill) + '</div>',
      '  <div class="km-fest-img-frame">',
      '    <img src="' + escapeHtml(imgUrl) + '" alt="Festival" class="km-fest-img" onerror="this.src=\'/images/krishna-janmashtami.jpg\'">',
      '  </div>',
      '  <h2 class="km-fest-title">' + escapeHtml(title) + '</h2>',
      '  <div class="km-fest-blessing">' + escapeHtml(blessing) + '</div>',
      bulletsHtml,
      '  <button type="button" class="km-fest-btn-accept" onclick="window.acceptFestivalBlessings()">',
      '    <span>🙏</span> <span>' + escapeHtml(cta) + '</span> <span>✨</span>',
      '  </button>',
      '  <div><button type="button" class="km-fest-btn-later" onclick="window.closeFestivalPopup()">बाद में देखें / बंद करें</button></div>',
      '</div>'
    ].join('\n');

    document.body.appendChild(overlay);
  }

  function createBadge(cfg) {
    if (document.getElementById(BADGE_ID)) return;
    var badge = document.createElement('div');
    badge.id = BADGE_ID;
    badge.title = (cfg && cfg.festival_name ? cfg.festival_name : 'त्योहार') + ' शुभकामनाएं देखें';
    badge.innerHTML = '<span>🪔</span> <span>' + escapeHtml(cfg && cfg.festival_name ? cfg.festival_name : 'पर्व शुभकामनाएं') + '</span> <span>✨</span>';
    badge.onclick = function () {
      openModal();
    };
    document.body.appendChild(badge);
  }

  function openModal() {
    if (!_activeConfig) return;
    createModal(_activeConfig);
    var modal = document.getElementById(MODAL_ID);
    if (!modal) return;

    setTimeout(function () {
      modal.classList.add('km-open');
    }, 40);
  }

  function closeModal() {
    var modal = document.getElementById(MODAL_ID);
    if (modal) modal.classList.remove('km-open');
    try {
      localStorage.setItem(DISMISS_KEY, Date.now().toString());
    } catch (e) {}
    if (_activeConfig) createBadge(_activeConfig);
  }

  function triggerPetalShower() {
    var colors = ['#f59e0b', '#fbbf24', '#f43f5e', '#10b981', '#fb7185', '#38bdf8'];
    var shapes = ['🌸', '🌼', '🏵️', '✨', '🪶', '🍃', '🪔'];
    var count = 30;

    for (var i = 0; i < count; i++) {
      (function (idx) {
        setTimeout(function () {
          var petal = document.createElement('div');
          petal.className = 'km-petal';
          petal.textContent = shapes[Math.floor(Math.random() * shapes.length)];
          petal.style.left = (Math.random() * 95) + 'vw';
          petal.style.top = '-10px';
          petal.style.fontSize = (16 + Math.random() * 18) + 'px';
          petal.style.color = colors[Math.floor(Math.random() * colors.length)];
          petal.style.animationDuration = (2.2 + Math.random() * 2) + 's';
          document.body.appendChild(petal);

          setTimeout(function () {
            if (petal.parentNode) petal.parentNode.removeChild(petal);
          }, 4500);
        }, idx * 60);
      })(i);
    }
  }

  function acceptBlessings() {
    triggerPetalShower();
    try {
      localStorage.setItem(DISMISS_KEY, Date.now().toString());
    } catch (e) {}

    var btn = document.querySelector('.km-fest-btn-accept');
    if (btn) {
      btn.innerHTML = '<span>🙏</span> <span>शुभकामनाएं स्वीकार की गईं! (धन्यवाद)</span> <span>🌺</span>';
      btn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
      btn.style.borderColor = '#34d399';
    }

    setTimeout(function () {
      closeModal();
    }, 1300);
  }

  function previewModal(customConfig) {
    _activeConfig = customConfig || _activeConfig || {};
    createModal(_activeConfig);
    var modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    setTimeout(function () {
      modal.classList.add('km-open');
    }, 40);
  }

  // Expose global methods
  window.openFestivalPopup = openModal;
  window.closeFestivalPopup = closeModal;
  window.acceptFestivalBlessings = acceptBlessings;
  window.previewFestivalPopup = previewModal;

  async function init() {
    // If browsing in admin panel, do not auto-popup
    if (window.location.pathname.indexOf('/admin') !== -1) {
      return;
    }

    var apiBase = window.KRASHIMITRA_API_BASE || '';
    try {
      var res = await fetch(apiBase + '/api/festival/config');
      var data = await res.json();
      if (!data.success || !data.is_live || !data.config) {
        var exM = document.getElementById(MODAL_ID);
        if (exM) exM.remove();
        var exB = document.getElementById(BADGE_ID);
        if (exB) exB.remove();
        return;
      }

      _activeConfig = data.config;

      var cooldownMs = (_activeConfig.cooldown_hours || 3) * 60 * 60 * 1000;
      var lastDismiss = 0;
      try {
        lastDismiss = parseInt(localStorage.getItem(DISMISS_KEY) || '0', 10);
      } catch (e) {}

      var isCoolingDown = (Date.now() - lastDismiss) < cooldownMs;

      if (!isCoolingDown) {
        setTimeout(function () {
          openModal();
        }, 700);
      } else {
        createBadge(_activeConfig);
      }
    } catch (e) {
      // Graceful offline fallback
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

