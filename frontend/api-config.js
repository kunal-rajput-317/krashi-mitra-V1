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

  window.KRASHIMITRA_API_BASE = isLocal
    ? 'http://' + (host || 'localhost') + ':8000'
    : 'https://krashi-mitra-v1.onrender.com';
  window.KRASHIMITRA_IS_LOCAL = isLocal;

  console.log('[KrashiMitra] API base =', window.KRASHIMITRA_API_BASE);
})();

// ── Google OAuth Client ID ────────────────────────────────────
window.KRASHIMITRA_GOOGLE_CLIENT_ID = "235912622385-faavoh67rvg0m126bj5af8ot3n2k0shd.apps.googleusercontent.com";

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

    const apiBase = window.KRASHIMITRA_API_BASE || 'https://krashi-mitra-v1.onrender.com';
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
