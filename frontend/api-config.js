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
  //   logged in  → profile.html   |   logged out → login.html (sign in)
  function avatarTarget() {
    const t = localStorage.getItem("krishi_token");
    return (t && t !== "null" && t !== "undefined") ? "profile.html" : "login.html";
  }
  btn.addEventListener("click", function (e) {
    e.preventDefault();
    window.location.href = avatarTarget();
  });

  const token = localStorage.getItem("krishi_token");
  if (token) {
    // Keep href in sync for hover/middle-click/right-click UX
    btn.href = "profile.html";

    const cachedAvatar = localStorage.getItem("user_avatar_url");
    if (cachedAvatar && cachedAvatar !== "null") {
      const apiBase = window.KRASHIMITRA_API_BASE || 'https://krashi-mitra-v1.onrender.com';
      const src = cachedAvatar.startsWith("/") ? apiBase + cachedAvatar : cachedAvatar;
      btn.innerHTML = `<img src="${src}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;">`;
    } else {
      const apiBase = window.KRASHIMITRA_API_BASE || 'https://krashi-mitra-v1.onrender.com';
      fetch(`${apiBase}/profile`, {
        headers: { "Authorization": `Bearer ${token}` }
      })
      .then(r => r.json())
      .catch(() => ({}))
      .then(res => {
        if (res.success && res.data) {
          if (res.data.avatar_url) {
            localStorage.setItem("user_avatar_url", res.data.avatar_url);
            const src = res.data.avatar_url.startsWith("/") ? apiBase + res.data.avatar_url : res.data.avatar_url;
            btn.innerHTML = `<img src="${src}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;">`;
          }
          if (res.data.full_name) {
            localStorage.setItem("user_name", res.data.full_name);
          }
        }
      });
    }
  } else {
    // Lead to login.html if not logged in
    btn.href = "login.html";
  }
});
