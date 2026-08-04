// ============================================================
// KrashiMitra — Mobile bottom tab bar
//
// The audience is almost entirely on phones, so the primary
// destinations get a native-app-style bottom bar: मंडी भाव · दुकान ·
// समाचार · अन्य (opens the existing sidebar drawer). Desktop never
// sees it (display:none above 768px).
//
// Auto-hide: scrolling down slides the bar away so content gets the
// full screen; any upward scroll brings it back. It also hides while
// a popup is open, piggybacking on fab-autohide's body.km-popup-open.
//
// Works on both kinds of pages:
//   - static frontend pages (index/shop/weather…): relative "shop.html"-style
//     links so Live Server dev keeps working (deployed, those 301 to the
//     extensionless URL);
//   - backend-rendered /bhav + /product pages: root-absolute links,
//     since a relative link from /bhav/wheat/up would resolve inside
//     the /bhav tree.
// मंडी भाव always uses the root-absolute /bhav link (below): the mandi data
// now lives only on that backend-rendered tree, so there is no relative
// "mandi.html" file to link to any more.
//
// Usage: include once per page —
//   <script src="bottomnav.js" defer></script>    (static pages)
//   <script src="/bottomnav.js" defer></script>   (backend _header)
// ============================================================
(function () {
  var GREEN = '#2d6a4f', GREY = '#6b7a72';

  // Root-level static pages (index/shop/weather) can use relative
  // "shop.html" links so Live Server dev works. But pages served from a
  // sub-path — the backend /bhav + /product trees, and the static /articles/
  // pages — must use root-absolute links, or a relative "shop.html" would
  // resolve inside that sub-path (e.g. /articles/shop.html → 404).
  var path = location.pathname;
  // KM_FORCE_ABS_NAV: set by 404.html, which Netlify serves at whatever
  // unknown URL was requested — relative links would resolve inside it.
  var SEO = window.KM_FORCE_ABS_NAV ||
    /^\/(bhav|product)(\/|$)/.test(path) || /\/articles\//.test(path);

  var LABELS = {
    mandi: { hi: 'मंडी भाव', en: 'Mandi Bhav', kn: 'ಮಂಡಿ ದರ' },
    shop:  { hi: 'दुकान',    en: 'Shop',       kn: 'ಅಂಗಡಿ' },
    news:  { hi: 'समाचार',   en: 'News',       kn: 'ಸುದ್ದಿ' },
    more:  { hi: 'अन्य',     en: 'More',       kn: 'ಇನ್ನಷ್ಟು' }
  };

  var ICONS = {
    mandi: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9h16M4 9l1.05-4.2a1 1 0 0 1 .97-.8h11.96a1 1 0 0 1 .97.8L20 9M5.2 9v9.5A1.5 1.5 0 0 0 6.7 20h10.6a1.5 1.5 0 0 0 1.5-1.5V9M9.4 20v-5.2h5.2V20"/></svg>',
    shop:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h1.9l2.2 10.4a1.6 1.6 0 0 0 1.57 1.26h7.66a1.6 1.6 0 0 0 1.56-1.22L20.6 7.4a.6.6 0 0 0-.58-.74H6.1"/><circle cx="9.5" cy="19" r="1.4" fill="currentColor" stroke="none"/><circle cx="16.5" cy="19" r="1.4" fill="currentColor" stroke="none"/></svg>',
    news:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="13.5" height="14" rx="1.5"/><path d="M17.5 8H20v9a2 2 0 0 1-2 2"/><path d="M7 9h5M7 12h7.5M7 15h7.5"/></svg>',
    more:  '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="7" height="7" rx="1.8"/><rect x="13" y="4" width="7" height="7" rx="1.8"/><rect x="4" y="13" width="7" height="7" rx="1.8"/><rect x="13" y="13" width="7" height="7" rx="1.8"/></svg>'
  };

  var TABS = [
    { key: 'mandi', rel: '/bhav',               abs: '/bhav',      match: /^\/bhav(\/|$)/ },
    { key: 'shop',  rel: 'shop.html',           abs: '/product/',  match: /^\/(product|shop)(\/|$)|\/shop\.html$/ },
    { key: 'news',  rel: 'articles/index.html', abs: '/articles/', match: /\/articles(\/|$)/ },
    { key: 'more' } // button — opens the sidebar drawer
  ];

  var STYLE_ID = 'km-bottomnav-css';
  var CSS =
    '.km-bn{position:fixed;left:0;right:0;bottom:0;z-index:3500;display:none;' +
    'background:#fff;border-top:1px solid #e6ece8;box-shadow:0 -4px 18px rgba(20,40,30,.08);' +
    'padding-bottom:env(safe-area-inset-bottom);' +
    'transform:translateY(0);transition:transform .28s ease}' +
    '.km-bn.km-bn-hide{transform:translateY(110%)}' +
    'body.km-popup-open .km-bn{transform:translateY(110%)}' +
    '.km-bn-inner{display:flex;align-items:stretch}' +
    '.km-bn-item{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;' +
    'padding:8px 4px 7px;margin:0;background:none;border:none;text-decoration:none;cursor:pointer;' +
    'position:relative;font-family:inherit;font-size:10.5px;font-weight:700;line-height:1.2;' +
    'color:' + GREY + ';-webkit-tap-highlight-color:transparent}' +
    '.km-bn-item svg{width:23px;height:23px;display:block}' +
    '.km-bn-item.active{color:' + GREEN + '}' +
    '.km-bn-item.active::before{content:"";position:absolute;top:0;left:50%;transform:translateX(-50%);' +
    'width:26px;height:3px;border-radius:0 0 4px 4px;background:' + GREEN + '}' +
    '@media(max-width:768px){.km-bn{display:block}' +
    'body.km-has-bn{padding-bottom:calc(64px + env(safe-area-inset-bottom))}}';

  function getLang() {
    var l;
    try { l = localStorage.getItem('km_lang'); } catch (e) {}
    return /^(hi|en|kn)$/.test(l) ? l : 'hi';
  }

  function injectCss() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  function openDrawer(e) {
    if (e) e.preventDefault();
    var ov = document.querySelector('.sidebar-drawer-overlay');
    if (ov) ov.classList.add('open');
  }

  function build() {
    if (document.querySelector('.km-bn')) return;

    var nav = document.createElement('nav');
    nav.className = 'km-bn';
    nav.setAttribute('aria-label', 'मुख्य नेविगेशन');

    var inner = document.createElement('div');
    inner.className = 'km-bn-inner';

    TABS.forEach(function (t) {
      var el;
      if (t.key === 'more') {
        el = document.createElement('button');
        el.type = 'button';
        el.addEventListener('click', openDrawer);
      } else {
        el = document.createElement('a');
        el.href = SEO ? t.abs : t.rel;
        if (t.match.test(path)) el.className = 'active';
      }
      el.className = 'km-bn-item' + (el.className ? ' ' + el.className : '');
      el.setAttribute('data-km-bn', t.key);
      el.innerHTML = ICONS[t.key] + '<span></span>';
      inner.appendChild(el);
    });

    nav.appendChild(inner);
    document.body.appendChild(nav);
    document.body.classList.add('km-has-bn');
    return nav;
  }

  var curLang = null;
  function applyLang() {
    var lang = getLang();
    if (lang === curLang) return;
    curLang = lang;
    [].forEach.call(document.querySelectorAll('.km-bn-item'), function (el) {
      var e = LABELS[el.getAttribute('data-km-bn')];
      var span = el.querySelector('span');
      if (e && span) span.textContent = e[lang] || e.hi;
    });
  }

  // Hide going down, show going up. Small deltas (address-bar jitter,
  // iOS bounce) are ignored; the bar never hides near the top.
  function autoHide(nav) {
    var lastY = window.pageYOffset || 0;
    window.addEventListener('scroll', function () {
      var y = window.pageYOffset || 0;
      if (y <= 0) { nav.classList.remove('km-bn-hide'); lastY = 0; return; }
      var d = y - lastY;
      if (Math.abs(d) < 6) return;
      if (d > 0 && y > 90) nav.classList.add('km-bn-hide');
      else nav.classList.remove('km-bn-hide');
      lastY = y;
    }, { passive: true });
  }

  function init() {
    injectCss();
    var nav = build();
    if (!nav) return;
    applyLang();
    autoHide(nav);
    // The language picker lives in the drawer (drawer-menu.js) and pages
    // have their own switchers — after any click, re-check km_lang so the
    // tab labels follow whichever switcher was used.
    document.addEventListener('click', function () {
      setTimeout(applyLang, 0);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
