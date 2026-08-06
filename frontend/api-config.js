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

  var defaultPort = location.port || '8000';
  // Production is served two ways: krashimitra.in (Netlify static + a handful
  // of proxied paths in _redirects — bhav/product/share/alerts/sitemap/llms
  // ONLY) and krashi-mitra-v1.onrender.com (the FastAPI app serving its own
  // frontend, same origin as the API). `location.origin` would be right on
  // the Render domain but silently 404s everything else (login, signup,
  // /auth/*, /profile, ...) on krashimitra.in since Netlify doesn't proxy
  // those paths. Always hitting the Render URL directly works on both —
  // it's a cross-origin call from krashimitra.in, but that origin is already
  // in the backend's CORS allowlist.
  // Render reassigned the subdomain when this service was recreated — the
  // plain name was already taken, so it now lives at the -oxdc URL below.
  // (old host, no longer live: https://krashi-mitra-v1.onrender.com)
  window.KRASHIMITRA_API_BASE = isLocal
    ? location.protocol + '//' + (host || 'localhost') + ':' + defaultPort
    : 'https://krashi-mitra-v1-oxdc.onrender.com';
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

    const apiBase = window.KRASHIMITRA_API_BASE || 'https://krashi-mitra-v1-oxdc.onrender.com';
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
