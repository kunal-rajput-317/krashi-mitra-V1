/* Krashi Mitra — shared analytics bootstrap.
   Loaded from <head> on every page (articles use ../analytics.js).
   Keep this file synchronous: inline page scripts rely on window.gtag
   and window.kmTrack existing right after this tag. */

(function () {
  var GA_ID      = 'G-493H1PDP64';
  var CLARITY_ID = 'xuojrm8av1';

  /* ── Google Analytics 4 ── */
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { dataLayer.push(arguments); };
  gtag('js', new Date());
  gtag('config', GA_ID);

  var ga = document.createElement('script');
  ga.async = 1;
  ga.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
  document.head.appendChild(ga);

  /* ── Microsoft Clarity (heatmaps + session recordings) ── */
  (function (c, l, a, r, i, t, y) {
    c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
    t = l.createElement(r); t.async = 1; t.src = 'https://www.clarity.ms/tag/' + i;
    y = l.getElementsByTagName(r)[0]; y.parentNode.insertBefore(t, y);
  })(window, document, 'clarity', 'script', CLARITY_ID);

  /* ── One call that reports to both ──
     kmTrack('mandi_crop_view', { crop: 'Wheat', state: 'Uttar Pradesh' })
     GA4 gets the full event; Clarity gets the name plus each value as a
     filterable tag, so you can pull up recordings of that exact action. */
  window.kmTrack = function (name, params) {
    params = params || {};
    try { if (window.gtag) gtag('event', name, params); } catch (e) {}
    try {
      if (window.clarity) {
        clarity('event', name);
        for (var k in params) {
          if (Object.prototype.hasOwnProperty.call(params, k) &&
              params[k] != null && params[k] !== '') {
            clarity('set', k, String(params[k]).slice(0, 255));
          }
        }
      }
    } catch (e) {}
  };
})();
