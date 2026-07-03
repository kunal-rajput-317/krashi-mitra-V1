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
