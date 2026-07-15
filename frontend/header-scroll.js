/* ============================================================
   KrashiMitra — shared scroll-aware header behaviour
   ------------------------------------------------------------
   Hides the amber .pre-topbar helpline strip on scroll-down,
   brings it back on scroll-up. Slides the whole #header-wrapper
   up by exactly the announcement bar's own height, so
   .top-utility-bar / .main-header / .commodity-navbar stay
   pinned and fully visible at viewport top — only the amber
   bar is hidden.

   Requires the page markup to wrap pre-topbar + top-utility-bar
   + main-header (+ commodity-navbar) in:
     <div class="header-wrapper" id="header-wrapper"> ... </div>
   followed immediately by:
     <div class="topbar-spacer" id="topbar-spacer"></div>

   Include once, near the end of <body>:
     <script src="/header-scroll.js"></script>   (or ../ from articles/)
   ============================================================ */
(function initScrollHeader() {
  const wrapper = document.getElementById('header-wrapper');
  const spacer  = document.getElementById('topbar-spacer');
  let lastScrollY = window.scrollY;
  let announcementH = 0;
  let ticking = false;

  function measureHeader() {
    const ann = document.querySelector('.pre-topbar');
    if (!ann || !wrapper || !spacer) return;
    announcementH = ann.getBoundingClientRect().height;
    spacer.style.height = wrapper.getBoundingClientRect().height + 'px';
  }
  function onScroll() {
    if (!ticking) {
      window.requestAnimationFrame(() => {
        const y = window.scrollY;
        wrapper.style.transform = (y > lastScrollY && y > announcementH)
          ? 'translateY(-' + announcementH + 'px)'
          : 'translateY(0)';
        lastScrollY = y;
        ticking = false;
      });
      ticking = true;
    }
  }
  measureHeader();
  window.addEventListener('resize', measureHeader);
  window.addEventListener('scroll', onScroll, { passive: true });
  // Some pages populate the blue quick-nav bar asynchronously (e.g. weather.html's
  // district chips), which grows #header-wrapper after this script's initial
  // measurement and silently desyncs the spacer — re-measure on any real size
  // change instead of only on window resize.
  if (window.ResizeObserver && wrapper) {
    new ResizeObserver(measureHeader).observe(wrapper);
  }
})();
