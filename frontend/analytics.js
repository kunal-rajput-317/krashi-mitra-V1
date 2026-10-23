/* Krashi Mitra — shared analytics bootstrap.
   Loaded from <head> on every page (articles use ../analytics.js).
   Keep this file synchronous: inline page scripts rely on window.gtag
   and window.kmTrack existing right after this tag. */

(function () {
  var GA_ID      = 'G-493H1PDP64';

  /* ── Google Analytics 4 ── */
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { dataLayer.push(arguments); };
  gtag('js', new Date());
  gtag('config', GA_ID);

  var ga = document.createElement('script');
  ga.async = 1;
  ga.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
  document.head.appendChild(ga);

  /* ── Event helper ──
     kmTrack('mandi_crop_view', { crop: 'Wheat', state: 'Uttar Pradesh' })
     Microsoft Clarity (session recordings) was removed on 24 Oct 2026: it
     recorded login, profile and AI-chat screens. Do not add a recorder back
     without the owner and the privacy policy (LEGAL_RULES §4). */
  window.kmTrack = function (name, params) {
    try { if (window.gtag) gtag('event', name, params || {}); } catch (e) {}
  };
})();
