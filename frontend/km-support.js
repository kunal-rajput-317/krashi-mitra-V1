// ============================================================
// KrashiMitra — put the ask where it can be seen.
//
// THE DEFECT THIS FIXES. Every money surface on this site was built and then
// left unreachable. /donate has worked for weeks and was linked from exactly
// two places — the server-rendered footers in bhav.py and news_page.py. It was
// not on the homepage, not on /weather, /khoj, /krashi_bajar, /meri_fasal, and
// not on any of the ~175 articles. /sponsor, the page a brand reads before
// paying us, had nowhere to be linked from at all. The site's most engaged
// audience — the homepage, which is the one page on this site with a healthy
// CTR — was never shown either.
//
// WHY A SCRIPT AND NOT 150 EDITS. Every static page carries its own hand-
// written <footer>. Adding two links to each of them is the same trap
// frontend/ads.js was written to escape: it works once, and then every new
// page is one more file somebody has to remember. This runs on every page
// already, so the links reach all the static pages and the ~14k server-
// rendered ones from one file — and a future footer link is one line here.
// See [[feedback_everything-must-be-automatic]].
//
// IT NEVER DUPLICATES AN EXISTING LINK. bhav.py and news_page.py already
// render both links server-side, and those must keep working with JavaScript
// off — an SSR page's footer is part of what Google indexes. So this checks
// for an existing href first and adds only what is missing, which means the
// two implementations can coexist and neither has to know about the other.
//
// WHAT IT MUST NOT BECOME. Not a banner, not a modal, not an interstitial, not
// a sticky bar. A farmer came here to check a price, and the one thing that
// would actually cost us money is making him feel solicited. Two words in a
// footer he can ignore is the whole intervention.
// ============================================================
(function () {
  if (window.__kmSupportInit) return;
  window.__kmSupportInit = 1;

  // Order matters: these are appended in sequence after whatever the page's
  // own footer already lists, so the site's own navigation stays first.
  //
  // /sponsor shipped 2026-09-25 — the footer link on every static page is
  // most of the page's internal linking, which is what gets it crawled.
  var LINKS = [
    { href: '/sponsor', text: 'विज्ञापन दें' },
    { href: '/donate',  text: 'सहयोग करें' }
  ];

  // Every footer link-row spelling in use across the site. The static pages
  // were written at different times and do not agree: .site-footer-links is
  // the homepage/shop generation, .km-footer-nav is the server shell, and
  // .footer-links is what a couple of the older article templates shipped.
  var ROWS = '.site-footer-links, .km-footer-nav, .footer-links';

  function alreadyHas(row, href) {
    var a = row.querySelectorAll('a[href]');
    for (var i = 0; i < a.length; i++) {
      // Compare the PATH, not the attribute: the server footer writes an
      // absolute https://krashimitra.in/donate and the static pages would get
      // a relative /donate, and a string compare would add a second copy.
      var p;
      try { p = new URL(a[i].href, location.href).pathname; } catch (e) { p = a[i].getAttribute('href') || ''; }
      if (p.replace(/\/$/, '') === href) return true;
    }
    return false;
  }

  function fill(row) {
    // The crop-links row in the server footer is also .km-footer-nav; it is
    // marked .km-footer-crops and is a list of भाव hubs, not site navigation.
    // Appending "सहयोग करें" to it would read as another crop.
    if (row.classList.contains('km-footer-crops')) return;
    for (var i = 0; i < LINKS.length; i++) {
      if (alreadyHas(row, LINKS[i].href)) continue;
      var a = document.createElement('a');
      a.href = LINKS[i].href;
      a.textContent = LINKS[i].text;
      // Inherits the row's own styling, whatever generation it is from — no
      // class of our own, so this cannot make one page's footer look unlike
      // the rest of it.
      row.appendChild(a);
    }
  }

  function init() {
    var rows = document.querySelectorAll(ROWS);
    for (var i = 0; i < rows.length; i++) fill(rows[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
