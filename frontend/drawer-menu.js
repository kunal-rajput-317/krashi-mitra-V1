// ============================================================
// KrashiMitra — Sidebar drawer: categorised accordion + language
//
// The drawer grew to ~13 flat links and farmers got lost in it. Rather than
// hand-editing the (per-page, slightly-different) drawer markup on every page,
// this component takes whatever flat `.sidebar-drawer-links` a page already
// ships and regroups it into labelled, collapsible sections at load time.
//
// Grouping is keyed off each link's emoji icon (the one thing identical across
// every page — hrefs are relative on some pages, absolute on others), so the
// same script produces the same menu everywhere. The original <a>/<button>
// nodes are MOVED (not cloned), so their href, onclick and `active` class
// survive. Each emoji is then swapped for a matching cartoonish olive SVG.
//
// The whole menu slider is also self-translating: this file owns the labels in
// hi/en/kn (backend /bhav + /product drawer items carry no data-t, so page-level
// i18n can't reach them), exposes a language dropdown in the drawer header, and
// defers to the page's own setLang()/pickLang() to translate the rest of the page.
// ============================================================
(function () {
  // ---- Shell bootstrap: ads.js ----------------------------------------
  // Ads are part of the page shell, and this file is the one script every page
  // on the site already loads — the 37 static articles, /bhav's ~14k server
  // pages and /product all pull it in. Bootstrapping ads.js from here means a
  // new article inherits ad placement by shipping the standard shell, with no
  // <script> tag to remember. ads.js self-guards, so a page that loads it
  // explicitly (bhav.py's _doc does, for mtime cache-busting) never double-runs.
  (function bootAds() {
    if (document.querySelector('script[src*="/ads.js"]')) return;
    var me = document.currentScript ||
             document.querySelector('script[src*="drawer-menu.js"]');
    if (!me || !me.src) return;
    var s = document.createElement('script');
    s.src = new URL('ads.js', me.src).href;   // resolves ../drawer-menu.js too
    s.defer = true;
    (document.head || document.documentElement).appendChild(s);
  })();

  // ---- Shell bootstrap: krashibook.js ---------------------------------
  // The drawer header shows the 📒 KrashiBook button only on pages that ship
  // the component, so it appeared on 6 pages and was missing everywhere else —
  // the same header behaving differently depending on where the farmer was.
  // Bootstrapping it here, exactly as ads.js is bootstrapped above, hands every
  // page the same header from one edit: the 17 static pages, the 60 articles,
  // and /bhav + /product's server-rendered pages alike.
  //
  // krashibook.js guards itself — it no-ops on shop.html (which ships its own
  // native bell) and against being included twice — so this is safe to fire
  // unconditionally. openKbook() below handles the shop.html case by falling
  // back to that native bell.
  (function bootKbook() {
    if (document.querySelector('script[src*="krashibook.js"]')) return;
    var me = document.currentScript ||
             document.querySelector('script[src*="drawer-menu.js"]');
    if (!me || !me.src) return;
    var s = document.createElement('script');
    s.src = new URL('krashibook.js', me.src).href;   // resolves ../drawer-menu.js too
    s.defer = true;
    (document.head || document.documentElement).appendChild(s);
  })();

  var OLIVE = '#6f7f3a', LEAF = '#b3c47f', CREAM = '#eef3e0';

  // Menu tiers are colour-coded so depth is readable at a glance: forest green
  // for anything at the top level (category headers + the pinned मुख्य/सहायता
  // shortcuts), sky blue for the links nested inside a category.
  //
  // FOREST is the shell's --km-green-dark. SKY is deliberately NOT the shell's
  // --sky (#2e86de): at 14px that only reaches 3.8:1 on white, under the 4.5:1
  // WCAG AA needs for text this size. #1b6ec2 is the nearest sky blue that
  // passes (5.2:1 on white, 4.8:1 on the cream hover).
  var FOREST = '#1a3c2e', SKY = '#1b6ec2';
  var FOREST_SOFT = '#f0f6f2', SKY_SOFT = '#eef5fd';   // hover tints
  var LANGS = ['hi', 'en', 'kn'];
  var LANG_NAMES = { hi: 'हिंदी', en: 'English', kn: 'ಕನ್ನಡ' };
  var LANG_SHORT = { hi: 'हिं', en: 'EN', kn: 'ಕ' };

  // Every string the menu slider renders, in all three languages.
  // Item entries are keyed by the emoji they replace; groups by "g_<key>".
  var LABELS = {
    menu:   { hi: 'मेनु',        en: 'Menu',          kn: 'ಮೆನು' },
    kbook:  { hi: 'कृषि बुक',    en: 'KrashiBook',    kn: 'ಕೃಷಿ ಬುಕ್' },
    g_tools:    { hi: 'टूल्स',        en: 'Tools',        kn: 'ಟೂಲ್ಸ್' },
    g_industry: { hi: 'कृषि उद्योग',  en: 'Agri-business', kn: 'ಕೃಷಿ ಉದ್ಯಮ' },
    g_news:     { hi: 'कृषि समाचार',  en: 'Agri News',    kn: 'ಕೃಷಿ ಸುದ್ದಿ' },
    g_other:    { hi: 'अन्य सेवाएं',  en: 'More Services', kn: 'ಇತರೆ ಸೇವೆಗಳು' },
    '🏠':  { hi: 'मुख्य',          en: 'Home',        kn: 'ಮುಖ್ಯ' },
    '🌤️': { hi: 'मौसम',          en: 'Weather',     kn: 'ಹವಾಮಾನ' },
    '🌱':  { hi: 'मेरी फसल',      en: 'My Crop',     kn: 'ನನ್ನ ಬೆಳೆ' },
    '🏪':  { hi: 'मंडी भाव',      en: 'Mandi Rates', kn: 'ಮಂಡಿ ದರ' },
    // '📈' सभी भाव सूची is retired — see DROP below. No label/icon needed: a
    // dropped link never reaches claim() or applyMenuLang().
    '🚜':  { hi: 'नेट भाव कैलकुलेटर', en: 'Net Price Tool', kn: 'ನೆಟ್ ದರ ಟೂಲ್' },
    '🛒':  { hi: 'दुकान',         en: 'Shop',        kn: 'ಅಂಗಡಿ' },
    '🤝':  { hi: 'व्यापारी लिस्टिंग', en: 'List Your Business', kn: 'ವ್ಯಾಪಾರಿ ನೋಂದಣಿ' },
    '🔍':  { hi: 'कृषि खोज',      en: 'Search',      kn: 'ಹುಡುಕಿ' },
    '🗺️': { hi: 'कृषि मानचित्र',  en: 'Map',         kn: 'ನಕ್ಷೆ' },
    '🧺':  { hi: 'कृषि बाज़ार',    en: 'Bazaar',      kn: 'ಬಜಾರ್' },
    '📰':  { hi: 'कृषि लेख',      en: 'Articles',    kn: 'ಲೇಖನಗಳು' },
    '🏛️': { hi: 'सरकारी योजना',   en: 'Govt Schemes', kn: 'ಸರ್ಕಾರಿ ಯೋಜನೆ' },
    '💬':  { hi: 'सहायता',        en: 'Help',        kn: 'ಸಹಾಯ' },
    '👤':  { hi: 'प्रोफ़ाइल',      en: 'Profile',     kn: 'ಪ್ರೊಫೈಲ್' }
  };

  // ---- Cartoonish olive icons, keyed by the emoji they replace ----
  var ICONS = {
    '🏠': '<svg viewBox="0 0 24 24"><path d="M11.3 3.5 3.6 10a1 1 0 0 0 .65 1.76H5.5V19A1.5 1.5 0 0 0 7 20.5h3v-4.2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v4.2h3A1.5 1.5 0 0 0 18.5 19v-7.24h1.25A1 1 0 0 0 20.4 10l-7.7-6.5a1.1 1.1 0 0 0-1.4 0Z" fill="currentColor"/></svg>',
    '🌤️': '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3" fill="' + LEAF + '"/><g stroke="' + LEAF + '" stroke-width="1.6" stroke-linecap="round"><path d="M9 2.5v1.4M9 12.1v1.4M2.9 8h1.4M13.7 8h1.4M4.7 3.7l1 1M12.3 11.3l1 1M13.3 3.7l-1 1M5.7 11.3l-1 1"/></g><path d="M9.2 19a3.4 3.4 0 0 1 .2-6.8 4.4 4.4 0 0 1 8.4 1.3A2.9 2.9 0 0 1 17.4 19H9.2Z" fill="currentColor"/></svg>',
    '🌱': '<svg viewBox="0 0 24 24"><path d="M12 20.5V12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M12.3 13.5c0-3 2.4-5.2 5.7-5.2 0 3-2.4 5.2-5.7 5.2Z" fill="' + LEAF + '"/><path d="M11.7 12c0-2.9-2.3-4.8-5.2-4.8 0 2.9 2.3 4.8 5.2 4.8Z" fill="currentColor"/><path d="M9 20.5h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    '🏪': '<svg viewBox="0 0 24 24"><path d="M4 9h16l-1.1-4.2A1 1 0 0 0 17.94 4H6.06a1 1 0 0 0-.96.8L4 9Z" fill="' + LEAF + '"/><path d="M5.2 9v9.5A1.5 1.5 0 0 0 6.7 20h10.6a1.5 1.5 0 0 0 1.5-1.5V9" fill="currentColor"/><rect x="9" y="13" width="6" height="7" rx="0.6" fill="' + LEAF + '"/></svg>',
    '🚜': '<svg viewBox="0 0 24 24"><path d="M5 7.5h4.2a1 1 0 0 1 .95.68L11.6 12H5a1 1 0 0 1-1-1V8.5a1 1 0 0 1 1-1Z" fill="' + LEAF + '"/><path d="M12.4 12l-1-3h4.3a1 1 0 0 1 .94.66L17.7 12Z" fill="currentColor"/><path d="M3 13.2h16.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="17" r="3.9" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="18.2" cy="18" r="2.8" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
    '🛒': '<svg viewBox="0 0 24 24"><path d="M3 4h1.9l2.2 10.4a1.6 1.6 0 0 0 1.57 1.26h7.66a1.6 1.6 0 0 0 1.56-1.22L20.6 7.4a.6.6 0 0 0-.58-.74H6.1" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="9.5" cy="19" r="1.6" fill="currentColor"/><circle cx="16.5" cy="19" r="1.6" fill="currentColor"/></svg>',
    '🤝': '<svg viewBox="0 0 24 24"><path d="M12.6 3.4 20 10.8a2 2 0 0 1 0 2.8l-6.4 6.4a2 2 0 0 1-2.8 0L4.4 13.6A2 2 0 0 1 3.8 12V5.4A2 2 0 0 1 5.8 3.4H12a2 2 0 0 1 .6 0Z" fill="' + LEAF + '" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="8.3" cy="8.3" r="1.6" fill="currentColor"/></svg>',
    '🔍': '<svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6" fill="' + LEAF + '" stroke="currentColor" stroke-width="2"/><path d="M15 15l5 5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
    '🗺️': '<svg viewBox="0 0 24 24"><path d="M9 4 4 6v14l5-2 6 2 5-2V4l-5 2-6-2Z" fill="' + LEAF + '" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9 4v14M15 6v14" stroke="currentColor" stroke-width="1.6"/></svg>',
    '🧺': '<svg viewBox="0 0 24 24"><path d="M8 10 10.6 5M16 10 13.4 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M4.3 10.2 5.6 18a1.5 1.5 0 0 0 1.48 1.25h9.84A1.5 1.5 0 0 0 18.4 18l1.3-7.8Z" fill="currentColor"/><path d="M3 10.2h18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/><path d="M9 13v3.4M12 13v3.4M15 13v3.4" stroke="' + LEAF + '" stroke-width="1.5" stroke-linecap="round"/></svg>',
    '📰': '<svg viewBox="0 0 24 24"><rect x="4" y="5" width="13.5" height="14" rx="1.5" fill="' + LEAF + '" stroke="currentColor" stroke-width="1.6"/><path d="M17.5 8H20v9a2 2 0 0 1-2 2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M7 9h5M7 12h7.5M7 15h7.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    '🏛️': '<svg viewBox="0 0 24 24"><path d="M12 3 3.5 7.4V9h17V7.4L12 3Z" fill="' + LEAF + '" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M6 10.5v6.5M10 10.5v6.5M14 10.5v6.5M18 10.5v6.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M4 19.5h16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
    '💬': '<svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9.5L5 19.5V16a2 2 0 0 1-1-2V6Z" fill="currentColor"/><path d="M8.5 9h7M8.5 12h4.5" stroke="' + CREAM + '" stroke-width="1.7" stroke-linecap="round"/></svg>',
    '👤': '<svg viewBox="0 0 24 24"><circle cx="12" cy="8.5" r="3.6" fill="currentColor"/><path d="M4.5 19.4a7.5 7.5 0 0 1 15 0 1 1 0 0 1-1 1.1h-13a1 1 0 0 1-1-1.1Z" fill="' + LEAF + '"/></svg>',
    'globe': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.4 2.5 14.6 0 17M12 3.5c-2.5 2.4-2.5 14.6 0 17"/></svg>'
  };

  // Group-header icons
  var GICON = {
    tools:    '<svg viewBox="0 0 24 24"><path d="M14.4 6.6a3.6 3.6 0 0 0 4.5 4.5L21 9.1 20 4.8 15.7 3.8 14.4 6.6Z" fill="' + LEAF + '" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M15.4 9.7 5.9 19.2A2 2 0 1 1 3.1 16.4L12.6 6.9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>',
    industry: '<svg viewBox="0 0 24 24"><path d="M12 21V8.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M12 8c0-2.1 1.5-3.7 3.6-3.7C15.6 6.4 14.1 8 12 8Zm0 0c0-2.1-1.5-3.7-3.6-3.7C8.4 6.4 9.9 8 12 8Z" fill="' + LEAF + '"/><path d="M12 13c0-1.9 1.4-3.3 3.3-3.3C15.3 11.6 13.9 13 12 13Zm0 0c0-1.9-1.4-3.3-3.3-3.3C8.7 11.6 10.1 13 12 13Zm0 4.4c0-1.9 1.4-3.3 3.3-3.3 0 1.9-1.4 3.3-3.3 3.3Zm0 0c0-1.9-1.4-3.3-3.3-3.3 0 1.9 1.4 3.3 3.3 3.3Z" fill="currentColor"/></svg>',
    news:     '<svg viewBox="0 0 24 24"><path d="M4 10v4a1 1 0 0 0 1 1h2l8 4V5L7 9H5a1 1 0 0 0-1 1Z" fill="currentColor"/><path d="M7 15v3.4a1 1 0 0 0 1 1h1.4a1 1 0 0 0 1-1V17" fill="' + LEAF + '"/><path d="M18 9.2a4 4 0 0 1 0 5.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/></svg>',
    other:    '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="1.6" fill="currentColor"/><rect x="13" y="4" width="7" height="7" rx="1.6" fill="' + LEAF + '"/><rect x="4" y="13" width="7" height="7" rx="1.6" fill="' + LEAF + '"/><rect x="13" y="13" width="7" height="7" rx="1.6" fill="currentColor"/></svg>'
  };

  var STYLE_ID = 'km-drawer-menu-css';
  var CSS =
    '.sidebar-drawer-header{display:flex;align-items:center}' +
    '.sidebar-drawer-link-icon{color:' + OLIVE + ';width:22px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}' +
    '.sidebar-drawer-link-icon svg{width:21px;height:21px;display:block}' +
    '.km-dg{display:flex;flex-direction:column}' +
    '.km-dg-head{display:flex;align-items:center;gap:11px;width:100%;box-sizing:border-box;' +
    'min-height:44px;padding:9px 12px;margin:0;background:none;border:none;border-radius:10px;' +
    'cursor:pointer;font-family:inherit;color:' + FOREST + ';text-align:left;transition:background .15s}' +
    '.km-dg-head:hover{background:' + FOREST_SOFT + '}' +
    '.km-dg-ico{color:' + FOREST + ';width:22px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}' +
    '.km-dg-ico svg{width:19px;height:19px;display:block}' +
    '.km-dg-label{flex:1;font-size:12px;font-weight:800;letter-spacing:.03em;text-transform:uppercase}' +
    '.km-dg-chev{font-size:11px;color:' + FOREST + ';opacity:.55;transition:transform .2s;flex-shrink:0}' +
    '.km-dg.open .km-dg-chev{transform:rotate(90deg)}' +
    '.km-dg-body{display:none;flex-direction:column;gap:2px;overflow:hidden;padding:2px 0 4px}' +
    '.km-dg.open .km-dg-body{display:flex}' +
    '.km-dg-body .sidebar-drawer-link{padding-left:26px}' +

    // ── Tier colours ────────────────────────────────────────
    // Two-selector specificity (0,2,0) beats the (0,1,0) `.sidebar-drawer-link`
    // colour that km-shell.css and 15 pages each declare, so no !important is
    // needed — and the .active rule below, at (0,3,0) + !important, still wins.
    //
    // Top level = the pinned मुख्य / सहायता / प्रोफ़ाइल shortcuts, which are
    // direct children of the list; anything the accordion nested sits in a
    // .km-dg-body instead. `>` is what keeps the two apart.
    '.sidebar-drawer-links > .sidebar-drawer-link{color:' + FOREST + '}' +
    '.sidebar-drawer-links > .sidebar-drawer-link .sidebar-drawer-link-icon{color:' + FOREST + '}' +
    '.sidebar-drawer-links > .sidebar-drawer-link:hover{background:' + FOREST_SOFT + '}' +

    '.km-dg-body .sidebar-drawer-link{color:' + SKY + '}' +
    '.km-dg-body .sidebar-drawer-link .sidebar-drawer-link-icon{color:' + SKY + '}' +
    '.km-dg-body .sidebar-drawer-link:hover{background:' + SKY_SOFT + '}' +

    // selected item = soft yellow (overrides each page\'s green .active rule,
    // and both tier colours above — "you are here" must outrank depth)
    '.sidebar-drawer-links .sidebar-drawer-link.active{background:#fef3c7!important;color:#4a3f1e!important;border-left-color:#eab308!important}' +
    '.sidebar-drawer-links .sidebar-drawer-link.active .sidebar-drawer-link-icon{color:#8a6d1f!important}' +
    '.km-drawer-sep{height:1px;background:#eef2ef;margin:6px 8px}' +
    // the old footer language row is now replaced by the header dropdown
    '.sidebar-drawer-footer{display:none}' +
    // header controls sit clustered on the right; the title soaks up the gap
    '.sidebar-drawer-title{margin-right:auto}' +
    '.km-kbook-hdr{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;padding:0;' +
    'font-size:17px;line-height:1;border-radius:50%;background:#f4f7ea;border:1.5px solid #e3ece5;cursor:pointer;margin-right:8px;flex-shrink:0}' +
    '.km-kbook-hdr:hover{background:#eaf0d8}' +
    '.km-kbook-hdr svg{width:18px;height:18px;display:block}' +
    // language dropdown
    '.km-lang{position:relative;margin-right:8px}' +
    '.km-lang-btn{display:flex;align-items:center;gap:5px;background:#f2f8f4;border:1.5px solid #e3ece5;' +
    'border-radius:16px;padding:5px 9px;font-family:inherit;font-size:12px;font-weight:700;color:#2d3748;cursor:pointer}' +
    '.km-lang-btn svg{width:14px;height:14px;color:' + OLIVE + '}' +
    '.km-lang-caret{font-size:9px;color:#8a958f}' +
    '.km-lang-menu{display:none;position:absolute;top:calc(100% + 6px);right:0;min-width:132px;background:#fff;' +
    'border:1px solid #e6ece8;border-radius:12px;box-shadow:0 8px 24px rgba(20,40,30,.14);padding:5px;z-index:20;flex-direction:column;gap:2px}' +
    '.km-lang-menu.open{display:flex}' +
    '.km-lang-menu button{text-align:left;background:none;border:none;border-radius:8px;padding:8px 10px;' +
    'font-family:inherit;font-size:13px;font-weight:600;color:#2d3748;cursor:pointer}' +
    '.km-lang-menu button:hover{background:#f2f8f4}' +
    '.km-lang-menu button.active{background:#eaf6ed;color:#2d6a4f;font-weight:800}';

  // Canonical order + category for every known drawer item, keyed by its emoji.
  var HOME = ['🏠'];
  var FOOTER = ['💬', '👤'];
  var GROUPS = [
    { key: 'tools',    ico: 'tools',    set: ['🌤️', '🌤', '🌱', '🗺️', '🗺'] }, // मौसम · मेरी फसल · कृषि मानचित्र
    { key: 'industry', ico: 'industry', set: ['🏪', '🚜', '🛒', '🤝'] },
    { key: 'news',     ico: 'news',     set: ['📰', '🏛️', '🏛'] },
    { key: 'other',    ico: 'other',    set: ['🔍', '🧺'] } // कृषि खोज · कृषि बाज़ार
  ];

  // Items retired from the menu, mapped to the item that inherits their
  // "you are here" highlight. मंडी भाव (🏪) and सभी भाव सूची (📈 → /bhav) were
  // two doors onto the same question and the farmer had to guess which one he
  // wanted; the menu now carries one, pointed at the fuller /bhav tree — which
  // is also the only mandi surface left now that mandi.html is retired.
  var DROP = { '📈': '🏪' };

  // Hrefs this file owns outright, whatever a page shipped. Root-absolute for
  // the same reason INVENTORY below is: drawer markup lives at several
  // directory depths and /bhav is served by the backend, so a relative path
  // would resolve wrong from /articles/ or from inside the /bhav tree.
  var HREF = { '🏪': '/bhav' };

  // ---- The canonical menu, in full -----------------------------------
  // The drawer used to be only as complete as whatever flat links each page
  // happened to ship, and no two page generations shipped the same set: the
  // /bhav + /product trees carry no मेरी फसल and no प्रोफ़ाइल, /dukanlisting
  // carries no मंडी भाव at all, and 404/login/terms/privacy/articles-index are
  // each missing something else. Same hamburger, different menu — the farmer
  // couldn't learn where anything was.
  //
  // So this file now guarantees the whole set instead of merely regrouping
  // what it finds: anything a page didn't ship gets synthesised here, which is
  // how 🚜 net-price and 🤝 dukanlisting already reached all ~44 static pages
  // plus the server-rendered trees from one edit. Pages written later inherit
  // a complete menu by shipping the standard shell.
  //
  // `at` marks the page the link points at, so a synthesised entry can still
  // show "you are here" (only reachable when the page itself omitted the link
  // — e.g. /dukanlisting, whose own drawer has no 🤝).
  //
  // Hrefs are root-absolute, and keep the .html suffix for the static pages:
  // the extensionless forms are the prod canonicals (Netlify 301s .html → them,
  // see frontend/_redirects) but only .html resolves under Live Server in dev,
  // and every page's own drawer already links the .html form.
  var INVENTORY = [
    { k: '🏠',  href: '/index.html',          at: /^\/(index\.html)?$/ },
    { k: '🌤️', href: '/weather.html',        at: /^\/weather(\.html)?$/ },
    { k: '🌱',  href: '/meri_fasal.html',     at: /^\/meri_fasal(\.html)?$/ },
    { k: '🗺️', href: '/map.html',            at: /^\/(map|naksha)(\.html)?(\/|$)/ },
    { k: '🏪',  href: '/bhav',                at: /^\/bhav(\/(?!net-price)|$)/ },
    { k: '🚜',  href: '/bhav/net-price',      at: /^\/bhav\/net-price/ },
    { k: '🛒',  href: '/shop.html',           at: /^\/shop(\.html)?$/ },
    { k: '🤝',  href: '/dukanlisting',        at: /^\/dukanlisting/ },
    { k: '🔍',  href: '/khoj.html',           at: /^\/khoj(\.html)?$/ },
    { k: '🧺',  href: '/krashi_bajar.html',   at: /^\/krashi_bajar(\.html)?$/ },
    { k: '📰',  href: '/articles/',           at: /^\/articles(\/|$)/ },
    { k: '🏛️', href: '/sarkari_yojana.html', at: /^\/sarkari_yojana(\.html)?$/ },
    { k: '💬',  href: '/chat.html',           at: /^\/chat(\.html)?$/ },
    { k: '👤',  href: '/profile.html',        at: /^\/profile(\.html)?$/ }
  ];

  function injectCss() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  function getLang() {
    var u;
    try { u = new URLSearchParams(location.search).get('lang'); } catch (e) {}
    if (u && /^(hi|en|kn)$/.test(u)) return u;
    var l;
    try { l = localStorage.getItem('km_lang'); } catch (e) {}
    return /^(hi|en|kn)$/.test(l) ? l : 'hi';
  }

  function iconOf(a) {
    var s = a.querySelector('.sidebar-drawer-link-icon');
    return s ? s.textContent.trim() : '';
  }

  // The text span of a drawer link = its first child span that isn't the icon.
  function labelSpan(a) {
    var kids = a.children;
    for (var i = 0; i < kids.length; i++) {
      if (!kids[i].classList || !kids[i].classList.contains('sidebar-drawer-link-icon')) return kids[i];
    }
    return null;
  }

  // Take ownership of a link: tag it with its emoji key, drop the page's data-t
  // (so page-level setLang won't fight us over this label), swap in the SVG.
  function claim(a, emoji) {
    a.setAttribute('data-km-key', emoji);
    var lab = labelSpan(a);
    if (lab && lab.removeAttribute) lab.removeAttribute('data-t');
    var ic = a.querySelector('.sidebar-drawer-link-icon');
    if (ic && ICONS[emoji]) ic.innerHTML = ICONS[emoji];
  }

  // Close the drawer, then open the KrashiBook modal via its existing button.
  // shop.html ships its own native bell instead of the book (krashibook.js
  // deliberately no-ops there), so fall back to that — otherwise the header
  // button we now inject on every page would be dead on exactly one of them.
  function openKbook(e) {
    if (e) e.preventDefault();
    var open = document.querySelector('.sidebar-drawer-overlay.open');
    if (open) open.classList.remove('open');
    var btn = document.getElementById('km-book-btn') ||
              document.getElementById('header-bell-btn');
    if (btn) btn.click();
  }

  // Emoji comparison, ignoring the variation selector: pages disagree on whether
  // they ship 🌤️/🌤, 🗺️/🗺, 🏛️/🏛, and a mismatch here would synthesise a
  // duplicate of a link the page already has.
  function keyOf(s) { return (s || '').replace(/️/g, ''); }

  // Top up the drawer to the full INVENTORY. Appends in document order; the
  // final position of each link comes from GROUPS, not from where it lands here.
  // Returns the links it added so build() can fold them into its list.
  function ensureItems(box) {
    var have = {};
    [].forEach.call(box.children, function (n) {
      if (n.classList && n.classList.contains('sidebar-drawer-link')) have[keyOf(iconOf(n))] = 1;
    });

    var added = [];
    INVENTORY.forEach(function (it) {
      if (have[keyOf(it.k)]) return;
      var a = document.createElement('a');
      a.href = it.href;
      a.className = 'sidebar-drawer-link';
      // Only a page that omitted its own link can land here, e.g. /bhav/net-price
      // (bhav.py renders every page in that module with active="bhav", so the
      // भाव entry is already lit) or /dukanlisting. Take the highlight over
      // rather than showing two "you are here"s.
      if (it.at && it.at.test(location.pathname)) {
        [].forEach.call(box.querySelectorAll('.sidebar-drawer-link.active'),
                        function (n) { n.classList.remove('active'); });
        a.className += ' active';
      }
      a.innerHTML = '<span class="sidebar-drawer-link-icon">' + it.k + '</span>' +
                    '<span>' + LABELS[it.k].hi + '</span>';
      box.appendChild(a);
      added.push(a);
    });
    return added;
  }

  // Retire DROP'd links and repoint the HREF'd ones. Done here rather than in
  // ~44 static pages plus bhav.py's server-rendered drawer, for the same reason
  // the grouping itself lives in this file: one edit, one source of truth, and
  // pages written later inherit it by shipping the standard shell.
  // Mutates `links` so the caller's list stays accurate.
  function fixupLinks(links) {
    var byIcon = {};
    links.forEach(function (a) {
      var i = iconOf(a);
      if (i && !byIcon[i]) byIcon[i] = a;
    });

    Object.keys(DROP).forEach(function (gone) {
      var a = byIcon[gone];
      if (!a) return;
      // Hand the highlight over before removing the node — bhav.py marks 📈
      // active on all ~14k of its pages, so dropping it silently would leave
      // the whole /bhav tree with no "you are here" at all.
      var heir = byIcon[DROP[gone]];
      if (heir && a.classList.contains('active')) heir.classList.add('active');
      if (a.parentNode) a.parentNode.removeChild(a);
      var at = links.indexOf(a);
      if (at !== -1) links.splice(at, 1);
      delete byIcon[gone];
    });

    Object.keys(HREF).forEach(function (i) {
      if (byIcon[i]) byIcon[i].setAttribute('href', HREF[i]);
    });
  }

  function build(box) {
    if (box.getAttribute('data-grouped')) return;

    var links = [].slice.call(box.children).filter(function (n) {
      return n.classList && n.classList.contains('sidebar-drawer-link');
    });
    // Bail before injecting: a drawer this sparse isn't the site shell (a stub,
    // a one-off page), and topping it up to the full menu would be rewriting
    // someone else's markup rather than making the shell consistent.
    if (links.length < 2) return;

    // Top up first, then fix up: 📈 hands its "you are here" to 🏪 below, and
    // on /dukanlisting — whose own drawer ships 📈 but no मंडी भाव — the heir
    // only exists because ensureItems just synthesised it.
    links = links.concat(ensureItems(box));
    fixupLinks(links);

    var byIcon = {};
    links.forEach(function (a) {
      var i = iconOf(a);
      if (i && !byIcon[i]) byIcon[i] = a;
    });

    var handled = [];
    function take(i) { var a = byIcon[i]; if (a) handled.push(a); return a; }
    function isHandled(a) { return handled.indexOf(a) !== -1; }

    var frag = document.createDocumentFragment();

    HOME.forEach(function (i) {
      var a = take(i);
      // मुख्य is a pinned shortcut, not a "category" — never show it selected.
      if (a) { a.classList.remove('active'); claim(a, i); frag.appendChild(a); }
    });

    var activeGroup = null, firstGroup = null;
    GROUPS.forEach(function (g) {
      var present = g.set.filter(function (i) { return byIcon[i]; });
      if (!present.length) return;

      var wrap = document.createElement('div');
      wrap.className = 'km-dg';
      wrap.setAttribute('data-km-g', g.key);

      var head = document.createElement('button');
      head.type = 'button';
      head.className = 'km-dg-head';
      head.setAttribute('aria-expanded', 'false');
      head.innerHTML =
        '<span class="km-dg-ico">' + (GICON[g.ico] || '') + '</span>' +
        '<span class="km-dg-label"></span>' +
        '<span class="km-dg-chev">▸</span>';

      var body = document.createElement('div');
      body.className = 'km-dg-body';

      var hasActive = false;
      present.forEach(function (i) {
        var a = take(i);
        claim(a, i);
        if (a.classList.contains('active')) hasActive = true;
        body.appendChild(a);
      });

      // Accordion: only one category open at a time.
      head.addEventListener('click', function () {
        var willOpen = !wrap.classList.contains('open');
        if (willOpen) {
          [].forEach.call(box.querySelectorAll('.km-dg.open'), function (o) {
            if (o === wrap) return;
            o.classList.remove('open');
            var hh = o.querySelector('.km-dg-head');
            if (hh) hh.setAttribute('aria-expanded', 'false');
          });
        }
        wrap.classList.toggle('open');
        head.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      });

      wrap.appendChild(head);
      wrap.appendChild(body);
      frag.appendChild(wrap);

      if (!firstGroup) firstGroup = wrap;
      if (hasActive) activeGroup = wrap;
    });

    var footSet = {};
    FOOTER.forEach(function (i) { footSet[i] = 1; });
    links.forEach(function (a) {
      if (isHandled(a) || footSet[iconOf(a)]) return;
      frag.appendChild(a); // unrecognised link — keep it visible
    });

    var footLinks = FOOTER.map(function (i) {
      var a = byIcon[i]; if (a) claim(a, i); return a;
    }).filter(Boolean);
    if (footLinks.length) {
      var sep = document.createElement('div');
      sep.className = 'km-drawer-sep';
      frag.appendChild(sep);
      footLinks.forEach(function (a) { frag.appendChild(a); });
    }

    box.innerHTML = '';
    box.appendChild(frag);
    box.setAttribute('data-grouped', '1');

    var toOpen = activeGroup || firstGroup;
    if (toOpen) {
      toOpen.classList.add('open');
      var h = toOpen.querySelector('.km-dg-head');
      if (h) h.setAttribute('aria-expanded', 'true');
    }
  }

  // Re-label the whole slider in `lang`. Owns menu title, group headings,
  // every item, and the KrashiBook entry.
  function applyMenuLang(lang) {
    function L(k) { var e = LABELS[k]; return e ? (e[lang] || e.hi) : null; }

    var title = document.querySelector('.sidebar-drawer-title');
    if (title) { title.removeAttribute('data-t'); var mt = L('menu'); if (mt) title.textContent = mt; }

    [].forEach.call(document.querySelectorAll('.sidebar-drawer-links [data-km-key]'), function (a) {
      var txt = L(a.getAttribute('data-km-key'));
      if (!txt) return;
      var lab = labelSpan(a);
      if (lab) lab.textContent = txt;
    });

    [].forEach.call(document.querySelectorAll('.km-dg[data-km-g]'), function (w) {
      var txt = L('g_' + w.getAttribute('data-km-g'));
      if (!txt) return;
      var lb = w.querySelector('.km-dg-label');
      if (lb) lb.textContent = txt;
    });

    var kb = document.querySelector('.km-kbook-hdr');
    if (kb) { var kt = L('kbook'); if (kt) { kb.setAttribute('aria-label', kt); kb.setAttribute('title', kt); } }

    var cur = document.querySelector('.km-lang-cur');
    if (cur) cur.textContent = LANG_NAMES[lang] || lang;
    [].forEach.call(document.querySelectorAll('.km-lang-menu [data-lang]'), function (b) {
      b.classList.toggle('active', b.getAttribute('data-lang') === lang);
    });
  }

  // Persist + retranslate the menu, then hand off to the page's own i18n so the
  // rest of the page follows (no-op on pages that don't ship one, e.g. /bhav).
  function chooseLang(lang) {
    try { localStorage.setItem('km_lang', lang); } catch (e) {}
    applyMenuLang(lang);
    applyHeaderLang(lang);
    if (typeof window.setLang === 'function') { try { window.setLang(lang); } catch (e) {} }
    else if (typeof window.pickLang === 'function') { try { window.pickLang(lang); } catch (e) {} }
  }
  // Exposed so the canonical header language picker (.km-hlang) works on every
  // page, including static articles that ship no setLang()/pickLang() of their own.
  window.KMChooseLang = chooseLang;

  // Reflect the current language in the header picker (short label + active row).
  function applyHeaderLang(lang) {
    [].forEach.call(document.querySelectorAll('.km-hlang-cur'), function (el) {
      el.textContent = LANG_SHORT[lang] || lang;
    });
    [].forEach.call(document.querySelectorAll('.km-hlang-menu [data-lang]'), function (b) {
      b.classList.toggle('active', b.getAttribute('data-lang') === lang);
    });
  }

  // Wire the header language picker: toggle its dropdown, pick a language, and
  // close on outside click. Safe to call when no .km-hlang exists on the page.
  function initHeaderLang() {
    [].forEach.call(document.querySelectorAll('.km-hlang'), function (wrap) {
      if (wrap.getAttribute('data-km-wired')) return;
      wrap.setAttribute('data-km-wired', '1');
      var btn = wrap.querySelector('.km-hlang-btn');
      var menu = wrap.querySelector('.km-hlang-menu');
      if (!btn || !menu) return;
      btn.addEventListener('click', function (e) { e.stopPropagation(); menu.classList.toggle('open'); });
      [].forEach.call(menu.querySelectorAll('[data-lang]'), function (o) {
        o.addEventListener('click', function (e) {
          e.stopPropagation();
          menu.classList.remove('open');
          chooseLang(o.getAttribute('data-lang'));
        });
      });
      document.addEventListener('click', function () { menu.classList.remove('open'); });
    });
  }

  function injectHeaderControls() {
    var header = document.querySelector('.sidebar-drawer-header');
    if (!header) return;
    var close = header.querySelector('.sidebar-drawer-close');

    // KrashiBook shortcut, sitting just left of the language button — only on
    // pages that actually ship the book component.
    if (document.querySelector('script[src*="krashibook.js"]') && !header.querySelector('.km-kbook-hdr')) {
      var kb = document.createElement('button');
      kb.type = 'button';
      kb.className = 'km-kbook-hdr';
      kb.setAttribute('aria-label', 'KrashiBook');
      kb.textContent = '📒'; // the original KrashiBook glyph, same as the floating button
      kb.addEventListener('click', openKbook);
      if (close) header.insertBefore(kb, close); else header.appendChild(kb);
    }

    if (header.querySelector('.km-lang')) return;

    var wrap = document.createElement('div');
    wrap.className = 'km-lang';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'km-lang-btn';
    btn.setAttribute('aria-label', 'Language');
    btn.innerHTML = ICONS.globe + '<span class="km-lang-cur"></span><span class="km-lang-caret">▾</span>';

    var menu = document.createElement('div');
    menu.className = 'km-lang-menu';
    LANGS.forEach(function (l) {
      var o = document.createElement('button');
      o.type = 'button';
      o.setAttribute('data-lang', l);
      o.textContent = LANG_NAMES[l];
      o.addEventListener('click', function (e) {
        e.stopPropagation();
        menu.classList.remove('open');
        chooseLang(l);
      });
      menu.appendChild(o);
    });

    btn.addEventListener('click', function (e) { e.stopPropagation(); menu.classList.toggle('open'); });
    document.addEventListener('click', function () { menu.classList.remove('open'); });

    wrap.appendChild(btn);
    wrap.appendChild(menu);
    if (close) header.insertBefore(wrap, close); else header.appendChild(wrap);
  }

  function init() {
    injectCss();
    var box = document.querySelector('.sidebar-drawer-links');
    if (box) build(box);
    injectHeaderControls();
    initHeaderLang();
    applyMenuLang(getLang());
    applyHeaderLang(getLang());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
