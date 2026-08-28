// ============================================================
// frontend/km-social.js
// कृषि मित्र's own channels, in one place: the header stickers, the drawer
// row, and the one-time invite popup.
//
// ── Why one file ──────────────────────────────────────────────
// The invite links are the kind of thing that changes (a channel gets
// recreated, Instagram arrives later). If a URL lived in the markup it would
// live in 140 static HTML files AND bhav.py's server shell, and the first edit
// would miss half of them. So the table below is the ONLY place a URL is
// written, and everything that shows a channel — the utility-bar stickers, the
// drawer row, the popup's buttons — reads it.
//
// Same reasoning as drawer-menu.js and dukan-promo.js: markup and styles ship
// together from the script, so a page opts in by loading the shared shell and
// nothing else.
//
// ── How it reaches every page ─────────────────────────────────
// drawer-menu.js bootstraps this file, exactly as it bootstraps ads.js and
// krashibook.js — that is the one script all 148 static pages and bhav.py's
// ~14k server-rendered pages already load. bhav.py's _doc also names it
// explicitly for the ?v=<mtime> cache-bust; the boot guard below makes the
// double-include a no-op.
//
// ── A blank url is off, not broken ────────────────────────────
// Same convention as backend/data/wa_channels.json: a channel with no https://
// url is simply not rendered, anywhere. So this file is safe to ship before
// the Facebook and Instagram accounts exist — those stickers appear the moment
// a link is pasted in, with no other edit. If NO channel has a url, nothing
// renders at all and the popup never fires.
// ============================================================
(function () {
  'use strict';

  if (window.__kmSocial) return;   // drawer-menu bootstrap + an explicit tag
  window.__kmSocial = 1;

  // ══════════════════════════════════════════════════════════
  // 1. THE LINKS — paste an invite URL here and you are done.
  // ══════════════════════════════════════════════════════════
  // WhatsApp : channel -> ⋮ -> Channel info -> copy link
  //            (https://whatsapp.com/channel/XXXXXXXXXXXXXXXXXX)
  // Facebook : the page's public URL (https://www.facebook.com/...)
  // Instagram: the profile URL       (https://www.instagram.com/...)
  //
  // Only https:// links are used; anything else counts as blank, so a
  // half-finished paste can never render a dead sticker.
  var LINKS = {
    wa: { url: 'https://whatsapp.com/channel/0029Vb97bUkFCCoV2dSa5P1y' },
    fb: { url: 'https://www.facebook.com/share/g/1DpF16q6Cd/' },
    ig: { url: 'https://www.instagram.com/krashimitra.in' }
  };

  // ══════════════════════════════════════════════════════════
  // 2. HOW OFTEN THE POPUP MAY ASK
  // ══════════════════════════════════════════════════════════
  // The brief was "make sure the user never gets frustrated with it", so the
  // popup is built around not asking rather than around asking:
  //
  //   · never during page load — it waits for proof of a real reader
  //     (DWELL_MS on the page AND a quarter of it scrolled, or PATIENT_MS
  //     parked on a page too short to scroll)
  //   · at most once per browsing session, whatever the page count
  //   · dismissed once -> silent for a week; twice -> three weeks;
  //     three times -> never again on this device
  //   · tapped a channel -> never again, permanently. They joined.
  //   · never on /pay, /admin or a sign-in page — that is someone mid-task,
  //     and interrupting a payment is the worst thing it could do
  //   · never on top of another prompt — the drawer, location.js's
  //     "अपना स्थान चालू करें" card, the login gate, KrashiBook — or while
  //     the farmer is typing into a field. It waits and takes its turn after.
  //     See BLOCKERS below; the first build stacked on the location card.
  //
  // Dismissing is deliberately over-served: the ✕, the "अभी नहीं" button, a tap
  // anywhere outside, Esc, a swipe down, and the Android back button all close
  // it. Back closing it (instead of leaving the site) is the one that matters
  // most on a phone.
  var DWELL_MS   = 12000;   // on-page time before the popup is even considered
  var PATIENT_MS = 30000;   // ...or this long, for a page too short to scroll
  var SCROLL_PCT = 0.25;
  var COOLDOWN_D = [7, 21]; // days of silence after the 1st and 2nd dismissal
  var MAX_SHOWS  = 3;       // after this many dismissals, never again
  var STORE      = 'km_social_invite';
  var SESSION    = 'km_social_invite_s';
  var SKIP_PATH  = /^\/(pay|admin|login|signup|register|reset)(\/|$|\.)/i;

  // ══════════════════════════════════════════════════════════
  // 3. Brand marks — 24×24, single path, fill:currentColor.
  // ══════════════════════════════════════════════════════════
  var ICON = {
    wa: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38c1.45.79 3.08 1.21 4.79 1.21h.01c5.46 0 9.9-4.45 9.9-9.91 0-2.65-1.03-5.14-2.9-7.01A9.816 9.816 0 0 0 12.04 2zm0 18.15h-.01c-1.5 0-2.97-.4-4.25-1.16l-.3-.18-3.12.82.83-3.04-.2-.31a8.196 8.196 0 0 1-1.26-4.37c0-4.54 3.7-8.24 8.25-8.24 2.2 0 4.27.86 5.83 2.42a8.19 8.19 0 0 1 2.41 5.83c0 4.55-3.7 8.24-8.24 8.24zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.17.25-.64.81-.78.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.12-.14.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.41-.42-.56-.42-.14-.01-.31-.01-.48-.01-.17 0-.43.06-.66.31-.23.25-.86.85-.86 2.07 0 1.22.89 2.4 1.01 2.57.12.17 1.75 2.67 4.23 3.74.59.26 1.05.41 1.41.52.59.19 1.13.16 1.56.1.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.08.14-1.18-.06-.11-.23-.17-.48-.29z"/></svg>',
    fb: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 8h-3v4h3v12h5v-12h3.642l.358-4h-4v-1.667c0-.955.192-1.333 1.115-1.333h2.885v-5h-3.808c-3.596 0-5.192 1.583-5.192 4.615v3.385z"/></svg>',
    ig: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>'
  };

  // ══════════════════════════════════════════════════════════
  // 4. Copy — hi / en / kn, the three languages the drawer offers.
  // ══════════════════════════════════════════════════════════
  // A Kannada reader on the Karnataka cluster is a real audience here (those
  // pages out-earn most of the site), so the popup speaks whatever km_lang the
  // drawer's language picker last stored.
  //
  // THE CHANNEL DOES NOT CARRY PRICES. The first draft led with "रोज़ का भाव,
  // सीधे आपके फ़ोन पर" and then repeated it in the body and in the first
  // bullet — three promises of a daily number the channel was never going to
  // post. A farmer who follows for a price he never receives unfollows, and
  // the invite has spent its one shot per device getting him there. The
  // numbers stay on /bhav, where they are actually updated every day; the
  // channel is what tells him there is something new. Do not put भाव back
  // into this copy without changing what the channel actually posts.
  var T = {
    hi: {
      follow: 'हमें फ़ॉलो करें',
      eyebrow: '📣 नया — कृषि मित्र चैनल',
      title: 'मौसम और योजना की खबर, सीधे आपके फ़ोन पर',
      body: 'मौसम की चेतावनी, सरकारी योजना और नए लेख — सब हमारे चैनल पर। कोई ग्रुप नहीं, कोई मैसेज की भीड़ नहीं।',
      b1: 'नए लेख और अपडेट सबसे पहले',
      b2: 'बिल्कुल मुफ़्त — जब चाहें छोड़ दें',
      b3: 'आपका नंबर किसी को नहीं दिखेगा',
      wa: 'WhatsApp चैनल जॉइन करें',
      fb: 'Facebook पर जुड़ें',
      ig: 'Instagram पर फ़ॉलो करें',
      no: 'अभी नहीं',
      close: 'बंद करें'
    },
    en: {
      follow: 'Follow us',
      eyebrow: '📣 New — the KrashiMitra channel',
      title: 'Weather and scheme news, straight to your phone',
      body: 'Weather warnings, government schemes and new guides — all on our channel. No group, no pile of messages.',
      b1: 'New guides and updates first',
      b2: 'Free — leave whenever you like',
      b3: 'Nobody can see your number',
      wa: 'Join the WhatsApp channel',
      fb: 'Join us on Facebook',
      ig: 'Follow us on Instagram',
      no: 'Not now',
      close: 'Close'
    },
    kn: {
      follow: 'ನಮ್ಮನ್ನು ಫಾಲೋ ಮಾಡಿ',
      eyebrow: '📣 ಹೊಸತು — ಕೃಷಿ ಮಿತ್ರ ಚಾನೆಲ್',
      title: 'ಹವಾಮಾನ ಮತ್ತು ಯೋಜನೆ ಸುದ್ದಿ, ನೇರವಾಗಿ ನಿಮ್ಮ ಫೋನ್‌ಗೆ',
      body: 'ಹವಾಮಾನ ಎಚ್ಚರಿಕೆ, ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು ಮತ್ತು ಹೊಸ ಲೇಖನಗಳು — ಎಲ್ಲವೂ ನಮ್ಮ ಚಾನೆಲ್‌ನಲ್ಲಿ. ಗುಂಪು ಇಲ್ಲ, ಸಂದೇಶಗಳ ಗದ್ದಲ ಇಲ್ಲ.',
      b1: 'ಹೊಸ ಲೇಖನ ಮತ್ತು ಅಪ್‌ಡೇಟ್ ಮೊದಲು',
      b2: 'ಉಚಿತ — ಯಾವಾಗ ಬೇಕಾದರೂ ಬಿಡಬಹುದು',
      b3: 'ನಿಮ್ಮ ಸಂಖ್ಯೆ ಯಾರಿಗೂ ಕಾಣಿಸುವುದಿಲ್ಲ',
      wa: 'WhatsApp ಚಾನೆಲ್ ಸೇರಿ',
      fb: 'Facebook ನಲ್ಲಿ ಸೇರಿ',
      ig: 'Instagram ನಲ್ಲಿ ಫಾಲೋ ಮಾಡಿ',
      no: 'ಈಗ ಬೇಡ',
      close: 'ಮುಚ್ಚಿ'
    }
  };

  var NAME  = { wa: 'WhatsApp', fb: 'Facebook', ig: 'Instagram' };
  var ORDER = ['wa', 'fb', 'ig'];

  function lang() {
    var l;
    try { l = localStorage.getItem('km_lang'); } catch (e) {}
    return T[l] ? l : 'hi';
  }
  function t(k) { var d = T[lang()]; return (d && d[k]) || T.hi[k]; }

  // Which channels are actually live right now.
  function live() {
    return ORDER.filter(function (k) {
      var u = LINKS[k] && LINKS[k].url;
      return typeof u === 'string' && /^https:\/\//i.test(u.trim());
    });
  }

  function track(name, key) {
    try { if (window.kmTrack) window.kmTrack(name, { channel: NAME[key] || key }); }
    catch (e) {}
  }

  // ══════════════════════════════════════════════════════════
  // 5. Styles
  // ══════════════════════════════════════════════════════════
  var CSS =
    // ── the stickers: one shared chip, three brand skins ──
    '.km-soc{display:inline-flex;align-items:center;gap:7px}' +
    '.km-soc-a{display:inline-flex;align-items:center;justify-content:center;' +
      'width:26px;height:26px;border-radius:50%;color:#fff;text-decoration:none;' +
      'box-shadow:0 1px 3px rgba(20,40,30,.2);' +
      'transition:transform .15s ease,box-shadow .15s ease}' +
    '.km-soc-a:hover{transform:translateY(-1px) scale(1.07);' +
      'box-shadow:0 3px 9px rgba(20,40,30,.28)}' +
    '.km-soc-a svg{width:14px;height:14px;display:block;fill:currentColor}' +
    '.km-soc-wa{background:#25d366}' +
    '.km-soc-fb{background:#1877f2}' +
    // Instagram has no flat brand colour — the gradient IS the mark.
    '.km-soc-ig{background:radial-gradient(circle at 30% 107%,' +
      '#fdf497 0%,#fdf497 5%,#fd5949 45%,#d6249f 60%,#285aeb 90%)}' +
    // ── drawer row: the phone's copy of the same three ──
    // .top-utility-bar is display:none under 721px and 98% of this site's
    // traffic is a phone, so stickers placed only there would be invisible to
    // almost everyone. The drawer is where a phone actually navigates.
    '.km-socd{display:flex;flex-direction:column;align-items:center;gap:9px;' +
      'padding:15px 12px 6px;margin-top:8px;border-top:1px solid #e7ece7}' +
    '.km-socd-t{font-size:12px;font-weight:700;color:#7c8983;letter-spacing:.2px}' +
    '.km-socd .km-soc{gap:16px}' +
    '.km-socd .km-soc-a{width:40px;height:40px}' +
    '.km-socd .km-soc-a svg{width:20px;height:20px}' +

    // ── the invite sheet ──
    // Phone first: a bottom sheet, thumb-reachable, every control at least
    // 44px tall. The centred desktop card is the variant.
    // Named "...-overlay", not "...-scrim", on purpose: fab-autohide.js hides
    // the floating AI-chat and map buttons whenever a fixed, full-screen element
    // whose class contains "overlay"/"modal"/"popup" is on screen. Matching that
    // convention is what stops the FAB sitting on top of the Instagram button —
    // which is exactly what the first build did. It re-checks on class changes,
    // so the .in that fades this in is what trips it.
    '.km-inv-overlay{position:fixed;inset:0;background:rgba(12,26,19,.55);' +
      'z-index:3900;opacity:0;transition:opacity .22s ease}' +
    '.km-inv-overlay.in{opacity:1}' +
    // z-index 3901: above the bottom nav (3500) and KrashiBook (3200), below
    // the drawer (4000) — which it is never open at the same time as anyway.
    '.km-inv{position:fixed;left:0;right:0;bottom:0;z-index:3901;box-sizing:border-box;' +
      'background:#fff;border-radius:20px 20px 0 0;max-height:88vh;overflow-y:auto;' +
      '-webkit-overflow-scrolling:touch;box-shadow:0 -10px 44px rgba(10,28,18,.3);' +
      'padding:0 18px calc(16px + env(safe-area-inset-bottom));' +
      'font-family:var(--km-font-body,\'DM Sans\',sans-serif);' +
      'transform:translateY(105%);transition:transform .3s cubic-bezier(.32,.72,0,1)}' +
    '.km-inv.in{transform:translateY(0)}' +
    // The grab handle is the affordance that says "this swipes away".
    '.km-inv-grab{width:42px;height:4px;border-radius:3px;background:#dde4de;' +
      'margin:9px auto 2px}' +
    // Both buttons are inside whatever CSS the host page ships, and several
    // pages draw a ring or a fill on every <button>. Reset first, then style.
    '.km-inv-x,.km-inv-no{-webkit-appearance:none;appearance:none;border:0;' +
      'box-shadow:none;outline:0;background:none;font-family:inherit;cursor:pointer}' +
    '.km-inv-x{position:absolute;top:8px;right:8px;width:40px;height:40px;' +
      'color:#8a958f;font-size:22px;line-height:1;padding:0;border-radius:50%}' +
    '.km-inv-x:hover{background:#f1f5f2;color:#1a3c2e}' +
    '.km-inv-hd{display:flex;align-items:center;gap:11px;margin:6px 0 10px;padding-right:40px}' +
    '.km-inv-logo{width:44px;height:44px;border-radius:50%;flex:none;object-fit:cover;' +
      'background:#eaf6ed;box-shadow:inset 0 0 0 1px rgba(45,106,79,.15)}' +
    '.km-inv-eyebrow{display:block;font-size:11px;font-weight:800;color:#7a5200;' +
      'margin-bottom:3px}' +
    '.km-inv-h{font-family:var(--km-font-serif,serif);font-size:17px;font-weight:800;' +
      'line-height:1.35;color:var(--km-green-dark,#1a3c2e);margin:0}' +
    '.km-inv-p{font-size:13px;line-height:1.6;color:var(--km-text-mid,#4a5a52);margin:0 0 11px}' +
    '.km-inv-list{list-style:none;padding:0;margin:0 0 14px;display:grid;gap:7px}' +
    '.km-inv-list li{position:relative;padding-left:24px;font-size:12.5px;' +
      'line-height:1.45;color:#3d4a43}' +
    '.km-inv-list li::before{content:\'\\2713\';position:absolute;left:0;top:0;' +
      'width:17px;height:17px;border-radius:50%;background:var(--km-green-mid,#2d6a4f);' +
      'color:#fff;font-size:10px;font-weight:800;display:flex;align-items:center;' +
      'justify-content:center}' +
    '.km-inv-btn{display:flex;align-items:center;justify-content:center;gap:9px;' +
      'width:100%;box-sizing:border-box;min-height:50px;padding:13px 16px;' +
      'border-radius:14px;color:#fff;text-decoration:none;font-size:14.5px;' +
      'font-weight:800;margin-bottom:9px;transition:filter .15s}' +
    '.km-inv-btn:hover{filter:brightness(1.07)}' +
    '.km-inv-btn svg{width:19px;height:19px;flex:none;fill:currentColor}' +
    // #128c7e, not the brighter #25d366: white on the light green misses even
    // the large-text contrast bar. A 26px sticker can be bright, a button can't.
    '.km-inv-wa{background:#128c7e}' +
    '.km-inv-fb{background:#1877f2}' +
    '.km-inv-ig{background:linear-gradient(45deg,#f09433,#dc2743 55%,#bc1888)}' +
    '.km-inv-no{display:block;width:100%;min-height:44px;margin-top:2px;' +
      'color:#7c8983;font-size:13.5px;font-weight:700}' +
    '.km-inv-no:hover{color:#1a3c2e}' +
    '@media(min-width:721px){' +
      '.km-inv{left:50%;right:auto;bottom:auto;top:50%;width:420px;' +
        'max-width:calc(100vw - 40px);border-radius:18px;padding:0 22px 20px;' +
        'transform:translate(-50%,-46%) scale(.97);opacity:0;' +
        'transition:transform .26s ease,opacity .26s ease}' +
      '.km-inv.in{transform:translate(-50%,-50%) scale(1);opacity:1}' +
      '.km-inv-grab{display:none}' +
      '.km-inv-hd{margin-top:20px}' +
      '.km-inv-h{font-size:19px}}' +
    // A farmer who has asked for less motion gets the sheet, not the slide.
    '@media(prefers-reduced-motion:reduce){' +
      '.km-inv,.km-inv-overlay,.km-soc-a{transition:none}}';

  function injectCSS() {
    if (document.getElementById('km-social-css')) return;
    var s = document.createElement('style');
    s.id = 'km-social-css';
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  // One sticker. `where` only distinguishes the analytics event.
  function chip(key, where) {
    var a = document.createElement('a');
    a.className = 'km-soc-a km-soc-' + key;
    a.href = LINKS[key].url.trim();
    a.target = '_blank';
    a.rel = 'noopener';
    a.title = NAME[key];
    a.setAttribute('aria-label', NAME[key]);
    a.innerHTML = ICON[key];
    a.addEventListener('click', function () {
      remember({ joined: 1 });          // they went; stop asking
      track('social_click_' + where, key);
    });
    return a;
  }

  function row(keys, where) {
    var box = document.createElement('span');
    box.className = 'km-soc';
    keys.forEach(function (k) { box.appendChild(chip(k, where)); });
    return box;
  }

  // ══════════════════════════════════════════════════════════
  // 6. Stickers in the utility bar, beside संपर्क
  // ══════════════════════════════════════════════════════════
  // Runtime injection rather than 140 edited files plus bhav.py's server
  // shell — the same call every other shell component makes. Idempotent, so a
  // page that later hard-codes the row does not end up with two.
  function mountUtilityIcons(keys) {
    var bars = document.querySelectorAll('.top-utility-right');
    for (var i = 0; i < bars.length; i++) {
      if (bars[i].querySelector('.km-soc')) continue;
      // 18 pages hard-code two <a class="top-utility-social-icon"> pointing at
      // a bare https://facebook.com with no account behind it. Drop them rather
      // than hide them: a hidden anchor is still a dead outbound link in the
      // markup, and all 35 of them live in exactly this container.
      var dead = bars[i].querySelectorAll('.top-utility-social-icon');
      for (var j = 0; j < dead.length; j++) dead[j].parentNode.removeChild(dead[j]);
      bars[i].appendChild(row(keys, 'header'));
    }
  }

  // ══════════════════════════════════════════════════════════
  // 7. Stickers in the drawer — the phone's half of the same job
  // ══════════════════════════════════════════════════════════
  // drawer-menu.js rebuilds .sidebar-drawer-links wholesale (it empties the box
  // and re-appends), so this has to run after that: it listens for the
  // km:drawer-ready event that file fires, and also appends straight away in
  // case the drawer was already built before this script parsed.
  function mountDrawerIcons(keys) {
    var box = document.querySelector('.sidebar-drawer-links');
    if (!box || box.querySelector('.km-socd')) return;
    var wrap = document.createElement('div');
    wrap.className = 'km-socd';
    var cap = document.createElement('span');
    cap.className = 'km-socd-t';
    cap.textContent = t('follow');
    wrap.appendChild(cap);
    wrap.appendChild(row(keys, 'drawer'));
    box.appendChild(wrap);
  }

  // ══════════════════════════════════════════════════════════
  // 8. The invite popup
  // ══════════════════════════════════════════════════════════
  function read() {
    try { return JSON.parse(localStorage.getItem(STORE) || '{}') || {}; }
    catch (e) { return {}; }
  }
  function remember(patch) {
    var s = read();
    for (var k in patch) if (patch.hasOwnProperty(k)) s[k] = patch[k];
    try { localStorage.setItem(STORE, JSON.stringify(s)); } catch (e) {}
  }

  // Everything that has to be true before we are even allowed to ask.
  function allowed() {
    var s = read();
    if (s.joined) return false;
    if ((s.n || 0) >= MAX_SHOWS) return false;
    if (s.until && Date.now() < s.until) return false;
    if (SKIP_PATH.test(location.pathname)) return false;
    try { if (sessionStorage.getItem(SESSION)) return false; } catch (e) {}
    return true;
  }

  // Everything else on this site that can put a card in front of the farmer.
  // The channel invite is the least urgent of them by a distance, so it always
  // yields rather than stacking: it waits for its turn and shows after.
  //
  // Raising our own z-index above theirs would "fix" the overlap and make the
  // real problem worse — two prompts arguing for the same tap. This list is
  // the fix. Anything fixed-position and interruptive added later belongs here.
  var BLOCKERS = [
    '.sidebar-drawer-overlay.open',  // drawer-menu.js — the slide-out menu
    '#km-loc-card',                  // location.js    — "अपना स्थान चालू करें"
    '.km-gate',                      // api-config.js  — the login gate
    '.km-mapdl-ov',                  // map-download.js
    '.km-book-overlay',              // krashibook.js
    'dialog[open]'
  ];

  function onScreen(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    var cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
  }

  // Is this a bad moment, right now? Re-checked every tick — the drawer, the
  // location card or a keyboard can appear at any point during the wait.
  function busy() {
    if (document.hidden) return true;
    for (var i = 0; i < BLOCKERS.length; i++) {
      if (onScreen(document.querySelector(BLOCKERS[i]))) return true;
    }
    var el = document.activeElement;
    if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return true;
    return false;
  }

  function readEnough(startedAt) {
    var waited = Date.now() - startedAt;
    if (waited >= PATIENT_MS) return true;        // parked long enough either way
    if (waited < DWELL_MS) return false;
    var doc = document.documentElement;
    var h = Math.max(doc.scrollHeight, document.body ? document.body.scrollHeight : 0);
    if (h <= window.innerHeight + 40) return false;   // nothing to scroll — wait it out
    return (window.pageYOffset + window.innerHeight) / h >= SCROLL_PCT;
  }

  function open(keys) {
    var scrim = document.createElement('div');
    scrim.className = 'km-inv-overlay';

    var sheet = document.createElement('div');
    sheet.className = 'km-inv';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-modal', 'true');
    sheet.setAttribute('aria-labelledby', 'km-inv-h');

    var btns = keys.map(function (k) {
      return '<a class="km-inv-btn km-inv-' + k + '" data-ch="' + k + '" ' +
             'href="' + LINKS[k].url.trim() + '" target="_blank" rel="noopener">' +
             ICON[k] + '<span>' + t(k) + '</span></a>';
    }).join('');

    sheet.innerHTML =
      '<div class="km-inv-grab"></div>' +
      '<button class="km-inv-x" type="button" aria-label="' + t('close') + '">&times;</button>' +
      '<div class="km-inv-hd">' +
        '<img class="km-inv-logo" src="/assets/logo-192.png" alt="" width="44" height="44">' +
        '<div><span class="km-inv-eyebrow">' + t('eyebrow') + '</span>' +
          '<h2 class="km-inv-h" id="km-inv-h">' + t('title') + '</h2></div>' +
      '</div>' +
      '<p class="km-inv-p">' + t('body') + '</p>' +
      '<ul class="km-inv-list"><li>' + t('b1') + '</li><li>' + t('b2') + '</li>' +
        '<li>' + t('b3') + '</li></ul>' +
      btns +
      '<button class="km-inv-no" type="button">' + t('no') + '</button>';

    document.body.appendChild(scrim);
    document.body.appendChild(sheet);

    var wasFocused = document.activeElement;
    var closed = false;

    // Android's back button should close the sheet, not leave the page. A
    // pushed history entry is what makes that possible; close() pops it back
    // off so the farmer's real back-history is exactly as they left it.
    var pushed = false;
    try { history.pushState({ kmInv: 1 }, ''); pushed = true; } catch (e) {}

    function teardown() {
      if (closed) return;
      closed = true;
      scrim.classList.remove('in');
      sheet.classList.remove('in');
      window.removeEventListener('popstate', onPop);
      document.removeEventListener('keydown', onKey);
      setTimeout(function () {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
      }, 320);
      try { if (wasFocused && wasFocused.focus) wasFocused.focus(); } catch (e) {}
    }

    // `popped` distinguishes "the back button closed us" (history has already
    // moved) from "a button closed us" (we still owe history a pop).
    function close(popped) {
      if (closed) return;
      if (!popped && pushed && history.state && history.state.kmInv) {
        history.back();      // fires onPop, which tears down
        return;
      }
      teardown();
    }

    // A dismissal is a fact worth storing: it sets the next cooldown, and the
    // third one retires the popup for good.
    //
    // note() is separate from close() because the back button reaches teardown
    // without passing through dismiss(). On a phone, back IS how this gets
    // closed — leaving that path unrecorded meant the popup asked again from
    // scratch on the visitor's next session, which is precisely the nagging
    // this whole component is built to avoid. `noted` keeps a double close
    // (dismiss -> history.back -> popstate) from counting twice.
    var noted = false;
    function note() {
      if (noted) return;
      noted = true;
      var s = read();
      var n = (s.n || 0) + 1;
      var days = COOLDOWN_D[n - 1];
      remember({ n: n, until: days ? Date.now() + days * 864e5 : 8.64e15 });
      track('social_invite_dismiss', 'popup');
    }

    function dismiss() { note(); close(false); }

    function onPop() { note(); teardown(); }
    function onKey(e) { if (e.key === 'Escape' || e.key === 'Esc') dismiss(); }

    window.addEventListener('popstate', onPop);
    document.addEventListener('keydown', onKey);
    scrim.addEventListener('click', dismiss);
    sheet.querySelector('.km-inv-x').addEventListener('click', dismiss);
    sheet.querySelector('.km-inv-no').addEventListener('click', dismiss);

    // Tapping a channel is a conversion, not a dismissal — never ask again.
    [].forEach.call(sheet.querySelectorAll('.km-inv-btn'), function (a) {
      a.addEventListener('click', function () {
        remember({ joined: 1 });
        track('social_invite_join', a.getAttribute('data-ch'));
        // close() unwinds through popstate, which would otherwise log this
        // conversion as a dismissal as well and quietly corrupt the funnel.
        noted = true;
        close(false);
      });
    });

    // Swipe the sheet down to dismiss — the gesture the grab handle promises.
    // Only from the top of the sheet, so swiping a scrolled sheet still scrolls.
    var y0 = null;
    sheet.addEventListener('touchstart', function (e) {
      y0 = sheet.scrollTop <= 0 ? e.touches[0].clientY : null;
    }, { passive: true });
    sheet.addEventListener('touchmove', function (e) {
      if (y0 === null) return;
      if (e.touches[0].clientY - y0 > 70) { y0 = null; dismiss(); }
    }, { passive: true });

    // Paint once at the closed position, then animate in on the next frame.
    requestAnimationFrame(function () {
      scrim.classList.add('in');
      sheet.classList.add('in');
      try { sheet.querySelector('.km-inv-x').focus({ preventScroll: true }); } catch (e) {}
    });

    try { sessionStorage.setItem(SESSION, '1'); } catch (e) {}
    track('social_invite_show', 'popup');
  }

  // GIVE_UP_MS: if something is still in the way ten minutes in — a location
  // card nobody answered, a login gate — this page's turn is simply over. No
  // point holding a timer for a visit that has clearly moved on.
  var GIVE_UP_MS = 600000;

  function armPopup(keys) {
    if (!allowed()) return;
    var startedAt = Date.now();
    var timer = setInterval(function () {
      if (!allowed() || Date.now() - startedAt > GIVE_UP_MS) { clearInterval(timer); return; }
      if (busy() || !readEnough(startedAt)) return;
      clearInterval(timer);
      open(keys);
    }, 1000);
  }

  // ══════════════════════════════════════════════════════════
  // 9. Boot
  // ══════════════════════════════════════════════════════════
  function init() {
    var keys = live();
    if (!keys.length) return;          // no link pasted yet — render nothing
    injectCSS();
    mountUtilityIcons(keys);
    mountDrawerIcons(keys);
    // drawer-menu.js may not have rebuilt the drawer yet; it announces when it has.
    document.addEventListener('km:drawer-ready', function () { mountDrawerIcons(keys); });
    armPopup(keys);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
