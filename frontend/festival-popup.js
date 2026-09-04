// ============================================================
// KrashiMitra — Dynamic Festival Wishes Pop-up Panel
// Managed via Admin Panel (/admin#festival-wishes)
// Dynamically reads /api/festival/config for image, duration, and status.
// ============================================================

(function () {
  'use strict';

  var MODAL_ID = 'km-festival-janmashtami-modal';
  var BADGE_ID = 'km-festival-reopen-badge';
  var STYLE_ID = 'km-festival-janmashtami-style';
  var DISMISS_KEY = 'km_festival_dismiss_ts';

  var _activeConfig = null;

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = [
      '#' + MODAL_ID + ' { position: fixed; inset: 0; z-index: 999999; display: flex; align-items: center; justify-content: center; padding: 14px; background: rgba(3, 10, 8, 0.76); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); opacity: 0; pointer-events: none; transition: opacity 0.32s cubic-bezier(0.16, 1, 0.3, 1); box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }',
      '#' + MODAL_ID + '.km-open { opacity: 1; pointer-events: auto; }',
      
      '.km-fest-card { position: relative; width: 100%; max-width: 410px; max-height: 92vh; overflow-y: auto; background: radial-gradient(circle at 50% 0%, #173d2f 0%, #0d221a 50%, #06110d 100%); border: 1.8px solid rgba(245, 158, 11, 0.6); border-radius: 24px; padding: 20px 18px 16px; color: #f8fafc; text-align: center; box-shadow: 0 25px 60px rgba(0,0,0,0.85), 0 0 35px rgba(245, 158, 11, 0.28), inset 0 1px 0 rgba(255,255,255,0.2); transform: scale(0.9) translateY(20px); transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1); box-sizing: border-box; scrollbar-width: thin; }',
      '#' + MODAL_ID + '.km-open .km-fest-card { transform: scale(1) translateY(0); }',
      
      '.km-fest-close { position: absolute; top: 12px; right: 12px; width: 34px; height: 34px; border-radius: 50%; background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.25); color: #e2e8f0; font-size: 18px; line-height: 1; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; z-index: 10; }',
      '.km-fest-close:hover { background: rgba(239,68,68,0.35); border-color: #ef4444; color: #fff; transform: rotate(90deg); }',

      '.km-fest-top-pill { display: inline-flex; align-items: center; gap: 6px; background: linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(16, 185, 129, 0.2)); border: 1px solid rgba(245, 158, 11, 0.5); padding: 4px 14px; border-radius: 20px; font-size: 11.5px; font-weight: 700; color: #fef08a; letter-spacing: 0.5px; margin-bottom: 12px; box-shadow: 0 2px 10px rgba(245, 158, 11, 0.2); }',
      
      '.km-fest-img-frame { position: relative; width: 100%; border-radius: 16px; overflow: hidden; border: 2px solid rgba(245, 158, 11, 0.65); box-shadow: 0 8px 25px rgba(0,0,0,0.5), 0 0 20px rgba(245, 158, 11, 0.3); margin-bottom: 14px; background: #0b1512; }',
      '.km-fest-img { width: 100%; height: auto; max-height: 230px; object-fit: cover; display: block; }',
      
      '.km-fest-title { font-size: 18.5px; font-weight: 900; line-height: 1.35; margin: 0 0 6px; background: linear-gradient(135deg, #fffbeb 0%, #fef08a 35%, #f59e0b 70%, #d97706 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-shadow: 0 2px 12px rgba(245, 158, 11, 0.3); }',
      
      '.km-fest-blessing { font-size: 12.5px; line-height: 1.55; color: #cbd5e1; margin-bottom: 13px; padding: 0 4px; }',
      
      '.km-fest-box { background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 12px; padding: 9px 12px; margin-bottom: 14px; font-size: 12px; line-height: 1.5; color: #a7f3d0; text-align: left; }',
      '.km-fest-box-item { display: flex; align-items: flex-start; gap: 7px; margin-bottom: 4px; }',
      '.km-fest-box-item:last-child { margin-bottom: 0; }',
      
      '.km-fest-btn-accept { width: 100%; background: linear-gradient(135deg, #f59e0b 0%, #d97706 50%, #b45309 100%); color: #ffffff; border: 1px solid rgba(254, 240, 138, 0.6); border-radius: 12px; padding: 11px 16px; font-size: 14px; font-weight: 800; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 4px 18px rgba(245, 158, 11, 0.45); transition: transform 0.15s, box-shadow 0.15s; }',
      '.km-fest-btn-accept:hover { transform: translateY(-1px); box-shadow: 0 6px 22px rgba(245, 158, 11, 0.65); }',
      '.km-fest-btn-accept:active { transform: translateY(1px); }',
      
      '.km-fest-btn-later { background: none; border: none; color: #94a3b8; font-size: 11.5px; font-weight: 600; margin-top: 8px; cursor: pointer; padding: 4px 10px; transition: color 0.2s; }',
      '.km-fest-btn-later:hover { color: #f1f5f9; text-decoration: underline; }',
      
      '#' + BADGE_ID + ' { position: fixed; bottom: 84px; right: 16px; z-index: 99990; display: flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #163d2f, #0d221a); border: 1.5px solid #f59e0b; border-radius: 30px; padding: 6px 13px; color: #fef08a; font-size: 11.5px; font-weight: 800; cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,0.5), 0 0 15px rgba(245,158,11,0.3); transition: transform 0.2s, box-shadow 0.2s; animation: km-fest-badge-pulse 2.4s infinite; }',
      '#' + BADGE_ID + ':hover { transform: scale(1.06); box-shadow: 0 8px 25px rgba(245,158,11,0.55); }',
      '@keyframes km-fest-badge-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.04); } }',

      // Petal confetti animation
      '.km-petal { position: fixed; pointer-events: none; z-index: 1000000; animation: km-petal-fall linear forwards; }',
      '@keyframes km-petal-fall { 0% { opacity: 1; transform: translateY(-20px) rotate(0deg) scale(1); } 100% { opacity: 0; transform: translateY(105vh) rotate(720deg) scale(0.6); } }'
    ].join('\n');
    document.head.appendChild(s);
  }

  function createModal(cfg) {
    var existing = document.getElementById(MODAL_ID);
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
    ensureStyles();

    var overlay = document.createElement('div');
    overlay.id = MODAL_ID;
    overlay.onclick = function (e) {
      if (e.target === overlay) closeModal();
    };

    var topPill = cfg.top_pill || '🪶 ॥ हरे कृष्ण ॥ 🪈';
    var imgUrl = window.KRISHNA_JANMASHTAMI_IMAGE || cfg.image_url || '/images/krishna-janmashtami.webp';
    var title = cfg.title || 'त्योहार शुभकामनाएं';
    var blessing = cfg.blessing_summary || 'कृषि मित्र परिवार की ओर से मंगलकामनाएं!';
    var b1 = cfg.bullet_1 || '';
    var b2 = cfg.bullet_2 || '';
    var cta = cfg.cta_text || '🙏 शुभकामनाएं स्वीकारें';

    var bulletsHtml = '';
    if (b1 || b2) {
      bulletsHtml = [
        '<div class="km-fest-box">',
        b1 ? '<div class="km-fest-box-item"><span>🌾</span><span>' + escapeHtml(b1) + '</span></div>' : '',
        b2 ? '<div class="km-fest-box-item"><span>🐄</span><span>' + escapeHtml(b2) + '</span></div>' : '',
        '</div>'
      ].join('');
    }

    overlay.innerHTML = [
      '<div class="km-fest-card">',
      '  <button type="button" class="km-fest-close" onclick="window.closeFestivalPopup()" title="बंद करें (Close)">✕</button>',
      '  <div class="km-fest-top-pill">' + escapeHtml(topPill) + '</div>',
      '  <div class="km-fest-img-frame">',
      '    <img src="' + escapeHtml(imgUrl) + '" alt="Festival" class="km-fest-img" onerror="this.src=\'/images/krishna-janmashtami.jpg\'">',
      '  </div>',
      '  <h2 class="km-fest-title">' + escapeHtml(title) + '</h2>',
      '  <div class="km-fest-blessing">' + escapeHtml(blessing) + '</div>',
      bulletsHtml,
      '  <button type="button" class="km-fest-btn-accept" onclick="window.acceptFestivalBlessings()">',
      '    <span>🙏</span> <span>' + escapeHtml(cta) + '</span> <span>✨</span>',
      '  </button>',
      '  <div><button type="button" class="km-fest-btn-later" onclick="window.closeFestivalPopup()">बाद में देखें / बंद करें</button></div>',
      '</div>'
    ].join('\n');

    document.body.appendChild(overlay);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, function (m) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m];
    });
  }

  function createBadge(cfg) {
    if (document.getElementById(BADGE_ID)) return;
    var badge = document.createElement('div');
    badge.id = BADGE_ID;
    badge.title = (cfg && cfg.festival_name ? cfg.festival_name : 'त्योहार') + ' शुभकामनाएं देखें';
    badge.innerHTML = '<span>🪔</span> <span>' + escapeHtml(cfg && cfg.festival_name ? cfg.festival_name : 'पर्व शुभकामनाएं') + '</span> <span>✨</span>';
    badge.onclick = function () {
      openModal();
    };
    document.body.appendChild(badge);
  }

  function openModal() {
    if (!_activeConfig) return;
    createModal(_activeConfig);
    var modal = document.getElementById(MODAL_ID);
    if (!modal) return;

    setTimeout(function () {
      modal.classList.add('km-open');
    }, 40);
  }

  function closeModal() {
    var modal = document.getElementById(MODAL_ID);
    if (modal) modal.classList.remove('km-open');
    try {
      localStorage.setItem(DISMISS_KEY, Date.now().toString());
    } catch (e) {}
    if (_activeConfig) createBadge(_activeConfig);
  }

  function triggerPetalShower() {
    var colors = ['#f59e0b', '#fbbf24', '#f43f5e', '#10b981', '#fb7185', '#38bdf8'];
    var shapes = ['🌸', '🌼', '🏵️', '✨', '🪶', '🍃', '🪔'];
    var count = 30;

    for (var i = 0; i < count; i++) {
      (function (idx) {
        setTimeout(function () {
          var petal = document.createElement('div');
          petal.className = 'km-petal';
          petal.textContent = shapes[Math.floor(Math.random() * shapes.length)];
          petal.style.left = (Math.random() * 95) + 'vw';
          petal.style.top = '-10px';
          petal.style.fontSize = (16 + Math.random() * 18) + 'px';
          petal.style.color = colors[Math.floor(Math.random() * colors.length)];
          petal.style.animationDuration = (2.2 + Math.random() * 2) + 's';
          document.body.appendChild(petal);

          setTimeout(function () {
            if (petal.parentNode) petal.parentNode.removeChild(petal);
          }, 4500);
        }, idx * 60);
      })(i);
    }
  }

  function acceptBlessings() {
    triggerPetalShower();
    try {
      localStorage.setItem(DISMISS_KEY, Date.now().toString());
    } catch (e) {}

    var btn = document.querySelector('.km-fest-btn-accept');
    if (btn) {
      btn.innerHTML = '<span>🙏</span> <span>शुभकामनाएं स्वीकार की गईं! (धन्यवाद)</span> <span>🌺</span>';
      btn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
      btn.style.borderColor = '#34d399';
    }

    setTimeout(function () {
      closeModal();
    }, 1300);
  }

  function previewModal(customConfig) {
    _activeConfig = customConfig || _activeConfig || {};
    createModal(_activeConfig);
    var modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    setTimeout(function () {
      modal.classList.add('km-open');
    }, 40);
  }

  // Expose global methods
  window.openFestivalPopup = openModal;
  window.closeFestivalPopup = closeModal;
  window.acceptFestivalBlessings = acceptBlessings;
  window.previewFestivalPopup = previewModal;

  async function init() {
    // If browsing in admin panel, do not auto-popup
    if (window.location.pathname.indexOf('/admin') !== -1) {
      return;
    }

    var apiBase = window.KRASHIMITRA_API_BASE || '';
    try {
      var res = await fetch(apiBase + '/api/festival/config');
      var data = await res.json();
      if (!data.success || !data.is_live || !data.config) {
        // Not live or inactive: remove any residual elements and exit
        var exM = document.getElementById(MODAL_ID);
        if (exM) exM.remove();
        var exB = document.getElementById(BADGE_ID);
        if (exB) exB.remove();
        return;
      }

      _activeConfig = data.config;

      var cooldownMs = (_activeConfig.cooldown_hours || 3) * 60 * 60 * 1000;
      var lastDismiss = 0;
      try {
        lastDismiss = parseInt(localStorage.getItem(DISMISS_KEY) || '0', 10);
      } catch (e) {}

      var isCoolingDown = (Date.now() - lastDismiss) < cooldownMs;

      if (!isCoolingDown) {
        setTimeout(function () {
          openModal();
        }, 700);
      } else {
        createBadge(_activeConfig);
      }
    } catch (e) {
      // Offline fallback: if network fails, don't crash page
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
