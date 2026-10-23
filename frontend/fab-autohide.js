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

    // AdSense rewrites the style of its own boxes many times a second while an
    // ad loads, and each of those used to cost a full popupOpen() — a style
    // recalc and a layout of the page (276 ms of forced reflow on an article in
    // Lighthouse). Nothing inside an ad, or inside the buttons themselves, can
    // be a popup, so changes there are skipped.
    var IGNORE = 'ins.adsbygoogle,.google-auto-placed,[id^="aswift"],.km-ad,' +
                 '.google-anno-skip,.ai-chat-fab,.map-fab';
    function ignorable(m) {
      var t = m.target.nodeType === 1 ? m.target : m.target.parentElement;
      return !!(t && t.closest && t.closest(IGNORE));
    }
    new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        if (!ignorable(records[i])) { schedule(); return; }
      }
    }).observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style"],
      childList: true,
    });
    window.addEventListener("resize", schedule);
    update();

    // The "AI से पूछें" label beside the chat button fades in for a few seconds
    // every 35 s. It used to be an infinite CSS animation, which keeps the
    // browser producing frames forever — on a low-end phone that alone held
    // the main thread busy most of the time the page sat open. A timer and a
    // class do the same thing with work only during the fades.
    var tips = document.querySelectorAll(".ai-fab-tip");
    if (tips.length) {
      var tipStyle = document.createElement("style");
      tipStyle.textContent =
        ".ai-fab-tip{animation:none!important;transition:opacity .6s ease-in-out}" +
        ".ai-fab-tip.km-tip-on{opacity:1}";
      document.head.appendChild(tipStyle);
      var setTips = function (on) {
        for (var j = 0; j < tips.length; j++) tips[j].classList.toggle("km-tip-on", on);
      };
      var showTip = function () {
        setTips(true);
        setTimeout(function () { setTips(false); }, 5000);
      };
      setTimeout(function () { showTip(); setInterval(showTip, 35000); }, 3000);
    }
  });
})();
