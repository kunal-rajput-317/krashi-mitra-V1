// ============================================================
// KrashiMitra — "नक्शा डाउनलोड करें": the state picker for map downloads
//
// Each नक्शा page used to offer a download for its own state only, so a farmer
// who landed on /map had no way to learn that a राजस्थान map exists at all.
// This file owns two things:
//
//   1. KM_STATE_MAPS — the ONE place that declares which states we can serve a
//      map for and where those files live. Add an entry here and the picker,
//      the district counts and the download filenames all follow, on every
//      page that loads this script. Nothing else needs editing.
//   2. The picker dialog — markup and CSS are injected from here, so the two
//      नक्शा pages (and any future one) get it from a single <script> tag.
//
// The trigger stays real static markup:
//     <a href="images/…-district-map.png" download="…" data-km-map-picker>
// so with JS blocked the button still downloads that page's own map. The click
// is intercepted only to offer the choice — never to create the link.
// ============================================================
(function () {
  'use strict';
  if (window.KM_STATE_MAPS) return;            // double-include guard

  // Paths resolve against this file's own URL, not the page's, so a नक्शा page
  // living one directory down (articles/…) still points at frontend/images.
  var ME = document.currentScript ||
           document.querySelector('script[src*="map-download.js"]');
  var BASE = (ME && ME.src) || location.href;
  var abs = function (p) { return new URL(p, BASE).href; };

  // ── served states ──────────────────────────────────────────
  // `districts` is the count baked into that state's generated map image, so it
  // matches what the farmer actually receives. Assets come from
  // make_state_maps.py — a state without generated images does not belong here.
  var STATES = {
    up: {
      hi: 'उत्तर प्रदेश', en: 'Uttar Pradesh', kn: 'ಉತ್ತರ ಪ್ರದೇಶ',
      districts: 75,
      png:  abs('images/up-ka-naksha-district-map.png'),
      file: 'up-ka-naksha-75-jile.png',
      page: abs('map.html')
    },
    rajasthan: {
      hi: 'राजस्थान', en: 'Rajasthan', kn: 'ರಾಜಸ್ಥಾನ',
      districts: 33,
      png:  abs('images/rajasthan-ka-naksha-district-map.png'),
      file: 'rajasthan-ka-naksha-33-jile.png',
      page: abs('rajasthan-ka-naksha.html')
    }
  };
  window.KM_STATE_MAPS = STATES;

  var T = {
    hi: { title: 'किस राज्य का नक्शा चाहिए?',
          sub:   'अपना राज्य चुनें — HD नक्शा तुरंत डाउनलोड होगा, बिल्कुल मुफ्त।',
          jile:  'जिले', dl: 'डाउनलोड', close: 'बंद करें',
          foot:  'बाकी राज्यों के नक्शे जल्द जोड़े जाएंगे।' },
    en: { title: 'Which state’s map do you want?',
          sub:   'Pick your state — the HD map downloads right away, free.',
          jile:  'districts', dl: 'Download', close: 'Close',
          foot:  'Maps for more states are coming soon.' },
    kn: { title: 'ಯಾವ ರಾಜ್ಯದ ನಕ್ಷೆ ಬೇಕು?',
          sub:   'ನಿಮ್ಮ ರಾಜ್ಯ ಆಯ್ಕೆಮಾಡಿ — HD ನಕ್ಷೆ ತಕ್ಷಣ ಡೌನ್‌ಲೋಡ್ ಆಗುತ್ತದೆ, ಉಚಿತ.',
          jile:  'ಜಿಲ್ಲೆಗಳು', dl: 'ಡೌನ್‌ಲೋಡ್', close: 'ಮುಚ್ಚಿ',
          foot:  'ಇನ್ನಷ್ಟು ರಾಜ್ಯಗಳ ನಕ್ಷೆ ಶೀಘ್ರದಲ್ಲೇ ಬರಲಿದೆ.' }
  };

  function lang() {
    var q = new URLSearchParams(location.search).get('lang');
    var l = q || localStorage.getItem('km_lang') || 'hi';
    return T[l] ? l : 'hi';
  }

  // ── styles ─────────────────────────────────────────────────
  // Injected rather than shipped in km-shell.css: the dialog only ever exists
  // after this script has run, so there is no unstyled frame to flash.
  var CSS = [
    // z-index clears everything that floats on these pages: the AI chat FAB and
    // the nav-loading overlay both sit at 9999, and a modal that the FAB pokes
    // through reads as a broken page.
    '.km-mapdl-ov{position:fixed;inset:0;z-index:10050;display:none;align-items:center;',
    'justify-content:center;background:rgba(15,23,20,.55);backdrop-filter:blur(3px);padding:18px}',
    '.km-mapdl-ov.open{display:flex}',
    '.km-mapdl{background:#fff;border-radius:16px;width:100%;max-width:430px;overflow:hidden;',
    'box-shadow:0 18px 50px rgba(0,0,0,.32);animation:km-mapdl-in .2s cubic-bezier(.16,1,.3,1);',
    "font-family:'DM Sans','Noto Sans Devanagari',sans-serif}",
    '@keyframes km-mapdl-in{from{opacity:0;transform:translateY(12px) scale(.98)}to{opacity:1;transform:none}}',
    '.km-mapdl-head{display:flex;gap:12px;align-items:flex-start;padding:18px 18px 12px}',
    '.km-mapdl-t{font-size:16.5px;font-weight:800;color:#1a3c2e;line-height:1.3}',
    '.km-mapdl-s{font-size:12.5px;color:#6b7d72;margin-top:4px;line-height:1.5}',
    '.km-mapdl-x{margin-left:auto;flex-shrink:0;width:32px;height:32px;border:none;border-radius:50%;',
    'background:#f2f5f3;color:#5b675f;font-size:14px;cursor:pointer;line-height:1}',
    '.km-mapdl-x:hover{background:#e6ebe8;color:#1c2b22}',
    '.km-mapdl-list{padding:2px 12px 14px;display:flex;flex-direction:column;gap:8px;',
    'max-height:52vh;overflow-y:auto}',
    '.km-mapdl-row{display:flex;align-items:center;gap:12px;padding:12px 14px;border-radius:12px;',
    'border:1.5px solid #e3ece5;background:#fff;text-decoration:none;color:#1a2e1e;cursor:pointer;',
    'transition:border-color .15s,background .15s}',
    '.km-mapdl-row:hover{border-color:#52b788;background:#f4faf6}',
    '.km-mapdl-row:focus-visible{outline:2px solid #2d6a4f;outline-offset:2px}',
    '.km-mapdl-ic{font-size:20px;line-height:1;flex-shrink:0}',
    '.km-mapdl-nm{display:flex;flex-direction:column;min-width:0}',
    '.km-mapdl-nm b{font-size:14.5px;font-weight:700}',
    '.km-mapdl-nm small{font-size:11.5px;color:#7a8a80;margin-top:2px}',
    '.km-mapdl-go{margin-left:auto;flex-shrink:0;background:#e9a825;color:#1a3c2e;font-size:12px;',
    'font-weight:800;padding:7px 12px;border-radius:8px;white-space:nowrap}',
    '.km-mapdl-foot{border-top:1px solid #eef2ef;padding:11px 18px;font-size:11.5px;color:#8a958f;',
    'background:#fafcfa}',
    '@media(max-width:520px){',
    '.km-mapdl-ov{align-items:flex-end;padding:0}',
    '.km-mapdl{max-width:none;border-radius:18px 18px 0 0;',
    'padding-bottom:env(safe-area-inset-bottom);',
    'animation:km-mapdl-up .22s cubic-bezier(.16,1,.3,1)}',
    '.km-mapdl-list{max-height:58vh}}',
    '@keyframes km-mapdl-up{from{transform:translateY(100%)}to{transform:none}}'
  ].join('');

  function injectCSS() {
    if (document.getElementById('km-mapdl-css')) return;
    var s = document.createElement('style');
    s.id = 'km-mapdl-css';
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  // ── file sizes ─────────────────────────────────────────────
  // Read off the file itself instead of being typed in here, so regenerating a
  // map can never leave a stale "392 KB" on the row. This host answers 200 with
  // an HTML page for a missing static file, so the header is trusted only when
  // the response really is the image.
  var sizes = {};
  function human(n) {
    return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB';
  }
  function loadSize(key) {
    if (key in sizes) { paintSize(key); return; }
    fetch(STATES[key].png, { method: 'HEAD' }).then(function (r) {
      var ct  = r.headers.get('content-type') || '';
      var len = parseInt(r.headers.get('content-length') || '', 10);
      sizes[key] = (r.ok && ct.indexOf('image/') === 0 && len > 0) ? human(len) : null;
      paintSize(key);
    }).catch(function () { sizes[key] = null; });
  }
  function paintSize(key) {
    var el = document.querySelector('.km-mapdl-row[data-state="' + key + '"] .km-mapdl-sz');
    if (el && sizes[key]) el.textContent = ' · ' + sizes[key];
  }

  // ── dialog ─────────────────────────────────────────────────
  var ov = null, lastFocus = null;

  function build() {
    injectCSS();
    var t = T[lang()], l = lang();

    if (!ov) {
      ov = document.createElement('div');
      ov.className = 'km-mapdl-ov';
      ov.id = 'km-mapdl-ov';
      ov.setAttribute('role', 'dialog');
      ov.setAttribute('aria-modal', 'true');
      ov.setAttribute('aria-labelledby', 'km-mapdl-t');
      ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
      document.body.appendChild(ov);
    }

    var rows = Object.keys(STATES).map(function (key) {
      var s = STATES[key];
      var name = s[l] || s.hi;
      return '<a class="km-mapdl-row" data-state="' + key + '" href="' + s.png + '" ' +
             'download="' + s.file + '">' +
               '<span class="km-mapdl-ic">🗺️</span>' +
               '<span class="km-mapdl-nm"><b>' + name + '</b>' +
                 '<small>' + s.districts + ' ' + t.jile + ' · HD PNG' +
                 '<span class="km-mapdl-sz"></span></small></span>' +
               '<span class="km-mapdl-go">⬇️ ' + t.dl + '</span>' +
             '</a>';
    }).join('');

    ov.innerHTML =
      '<div class="km-mapdl">' +
        '<div class="km-mapdl-head"><div>' +
          '<div class="km-mapdl-t" id="km-mapdl-t">' + t.title + '</div>' +
          '<div class="km-mapdl-s">' + t.sub + '</div></div>' +
          '<button class="km-mapdl-x" type="button" aria-label="' + t.close + '">✕</button>' +
        '</div>' +
        '<div class="km-mapdl-list">' + rows + '</div>' +
        '<div class="km-mapdl-foot">' + t.foot + '</div>' +
      '</div>';

    ov.querySelector('.km-mapdl-x').addEventListener('click', close);
    ov.querySelectorAll('.km-mapdl-row').forEach(function (a) {
      a.addEventListener('click', function () {
        if (window.gtag) gtag('event', 'map_download', { state: a.dataset.state });
        close();                       // the download itself is the <a>'s job
      });
    });
    Object.keys(STATES).forEach(loadSize);
  }

  function open() {
    lastFocus = document.activeElement;
    build();
    ov.classList.add('open');
    document.body.style.overflow = 'hidden';
    var first = ov.querySelector('.km-mapdl-row');
    if (first) first.focus();
  }

  function close() {
    if (!ov) return;
    ov.classList.remove('open');
    document.body.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && ov && ov.classList.contains('open')) close();
  });

  window.kmMapDownload = open;

  // ── wiring ─────────────────────────────────────────────────
  // Delegated, so a trigger rendered later (or by another component) works too.
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest && e.target.closest('[data-km-map-picker]');
    if (!trigger) return;
    e.preventDefault();               // the href stays as the no-JS fallback
    open();
  });
})();
