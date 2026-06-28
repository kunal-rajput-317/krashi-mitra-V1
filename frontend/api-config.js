// ============================================================
// KrashiMitra — Frontend API base auto-detection
// ------------------------------------------------------------
// When the page is opened locally (Live Server, file://, localhost,
// 127.0.0.1, or a LAN IP), API calls go to your LOCAL backend at
// http://<host>:8000. In production they go to the Render server.
//
// Override manually if needed BEFORE this script loads, e.g.:
//   <script>window.KRASHIMITRA_API_BASE = 'http://localhost:8000';</script>
//   <script src="api-config.js"></script>
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

  console.log('[KrashiMitra] API base =', window.KRASHIMITRA_API_BASE);
})();
