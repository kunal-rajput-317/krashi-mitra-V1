// ============================================================
// KrashiMitra — Auto-hide floating buttons during popups
// ------------------------------------------------------------
// Hides the floating AI-chat button and Map button whenever any
// popup / modal / overlay card is open, then restores them when
// it closes. Works on every page with no changes to modal code.
//
// How it detects an open popup: in this app every real popup is a
// full-screen `position: fixed` overlay that defaults to
// `display:none` and is toggled visible. Decorative overlays use
// `position: absolute`, so the fixed-check keeps them out.
//
// Usage: include once per page, e.g.
//   <script src="fab-autohide.js"></script>      (root pages)
//   <script src="../fab-autohide.js"></script>   (articles/)
// ============================================================
(function () {
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var fabs = document.querySelectorAll(".ai-chat-fab, .map-fab");
    if (!fabs.length) return; // no floating buttons on this page

    // Inject the hide rule once.
    var style = document.createElement("style");
    style.textContent =
      "body.km-popup-open .ai-chat-fab," +
      "body.km-popup-open .map-fab{" +
      "opacity:0!important;visibility:hidden!important;pointer-events:none!important;" +
      "transition:opacity .15s ease,visibility .15s ease;}";
    document.head.appendChild(style);

    var SEL =
      '[class*="overlay"],[class*="modal"],[class*="popup"],[class*="lightbox"],[class*="dialog"]';

    function popupOpen() {
      var vw = window.innerWidth, vh = window.innerHeight;
      var els = document.querySelectorAll(SEL);
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        if (el.classList.contains("ai-chat-fab") || el.classList.contains("map-fab")) continue;
        var cs = window.getComputedStyle(el);
        if (cs.position !== "fixed") continue; // real popups are fixed overlays
        if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0) continue;
        var r = el.getBoundingClientRect();
        if (r.width >= vw * 0.6 && r.height >= vh * 0.5) return true; // covers the screen
      }
      return false;
    }

    var scheduled = false;
    function update() {
      scheduled = false;
      var open = popupOpen();
      if (document.body.classList.contains("km-popup-open") !== open) {
        document.body.classList.toggle("km-popup-open", open);
      }
    }
    function schedule() {
      if (!scheduled) { scheduled = true; window.requestAnimationFrame(update); }
    }

    new MutationObserver(schedule).observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style"],
      childList: true,
    });
    window.addEventListener("resize", schedule);
    update();
  });
})();
