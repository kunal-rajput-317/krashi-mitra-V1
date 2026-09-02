// ============================================================
// KrashiMitra — Utility Tools Gamification & Habit Engine (km-gamify.js)
//
// Encourages daily engagement & retention:
//  - Mandi Bhav streak (e.g. "7 दिन लगातार भाव चेक किया 🌾")
//  - Meri Fasal crop logging & stage tracking streaks
//  - Utility tools badges (Mandi, Weather, Calculator, News)
//  - XP, Farmer Levels (नौसिखिया → सक्रिय → प्रगतिशील → कृषि रत्न)
//  - Celebratory Milestone Toasts + WhatsApp Shareable Badges
// ============================================================

(function (window, document) {
  'use strict';

  var STORAGE_KEY = 'km_gamify_v1';

  var BADGES_DEF = {
    'mandi_1': {
      id: 'mandi_1',
      title: 'पहला भाव चेक',
      title_en: 'First Price Check',
      desc: 'पहली बार मंडी भाव चेक किया',
      desc_en: 'Checked Mandi rates for the first time',
      emoji: '🌾',
      xp: 20,
      category: 'mandi'
    },
    'mandi_3': {
      id: 'mandi_3',
      title: '3-दिन मंडी भाव स्ट्रीक',
      title_en: '3-Day Price Streak',
      desc: '3 दिन लगातार मंडी भाव ट्रैक किया 🔥',
      desc_en: 'Tracked mandi prices for 3 consecutive days',
      emoji: '🔥',
      xp: 50,
      category: 'mandi'
    },
    'mandi_7': {
      id: 'mandi_7',
      title: '7 दिन भाव पारखी 🌾',
      title_en: '7-Day Price Master',
      desc: '7 दिन लगातार मंडी भाव देखा — बाज़ार का सच्चा पारखी!',
      desc_en: 'Checked Mandi rates 7 days in a row — true market expert!',
      emoji: '⭐',
      xp: 120,
      category: 'mandi'
    },
    'mandi_14': {
      id: 'mandi_14',
      title: '14 दिन बाज़ार योद्धा 🏆',
      title_en: '14-Day Market Guru',
      desc: '14 दिन लगातार भाव पर नज़र रखी',
      desc_en: '14 consecutive days of checking market rates',
      emoji: '🏅',
      xp: 250,
      category: 'mandi'
    },
    'mandi_30': {
      id: 'mandi_30',
      title: '30 दिन कृषि सम्राट 👑',
      title_en: '30-Day Mandi Legend',
      desc: 'पूरे 1 महीने तक रोज़ भाव चेक किया — सटीक व्यापार!',
      desc_en: '30 straight days of market vigilance — master trader!',
      emoji: '👑',
      xp: 500,
      category: 'mandi'
    },
    'fasal_1': {
      id: 'fasal_1',
      title: 'फसल रक्षक 🌱',
      title_en: 'Crop Custodian',
      desc: 'मेरी फसल में पहली फसल जोड़ी',
      desc_en: 'Added your first crop in Meri Fasal',
      emoji: '🌱',
      xp: 30,
      category: 'fasal'
    },
    'fasal_log': {
      id: 'fasal_log',
      title: 'जागरूक किसान 🚜',
      title_en: 'Vigilant Farmer',
      desc: 'फसल कैलेंडर व साप्ताहिक काम चेक किए',
      desc_en: 'Monitored crop calendar & weekly agricultural advisory',
      emoji: '🌿',
      xp: 40,
      category: 'fasal'
    },
    'calc_1': {
      id: 'calc_1',
      title: 'स्मार्ट व्यापारी 📊',
      title_en: 'Smart Calculator',
      desc: 'नेट भाव व मुनाफा कैलकुलेटर का इस्तेमाल किया',
      desc_en: 'Used Net Price & Profit Calculator tool',
      emoji: '🚜',
      xp: 30,
      category: 'tools'
    },
    'weather_1': {
      id: 'weather_1',
      title: 'मौसम विज्ञानी 🌤️',
      title_en: 'Weather Watcher',
      desc: 'बारिश व स्प्रे मौसम पूर्वानुमान चेक किया',
      desc_en: 'Checked rain and spray weather forecast',
      emoji: '🌤️',
      xp: 25,
      category: 'tools'
    },
    'news_reader': {
      id: 'news_reader',
      title: 'कृषि ज्ञान प्रेमी 📰',
      title_en: 'Agri News Reader',
      desc: 'कृषि न्यूज़ व समाचार बुलेटिन पढ़े या सुने',
      desc_en: 'Read or listened to agricultural news bulletins',
      emoji: '📰',
      xp: 25,
      category: 'news'
    }
  };

  var LEVELS = [
    { level: 1, name_hi: 'नौसिखिया किसान', name_en: 'Beginner Farmer', minXp: 0, emoji: '🌱', badgeColor: '#4b5563' },
    { level: 2, name_hi: 'सक्रिय कृषक', name_en: 'Active Farmer', minXp: 100, emoji: '🌾', badgeColor: '#2d6a4f' },
    { level: 3, name_hi: 'प्रगतिशील किसान', name_en: 'Progressive Farmer', minXp: 300, emoji: '🚜', badgeColor: '#1b6ec2' },
    { level: 4, name_hi: 'कृषि रत्न', name_en: 'Master Agri Champion', minXp: 700, emoji: '👑', badgeColor: '#e9a825' }
  ];

  function getTodayIso() {
    var d = new Date();
    var yyyy = d.getFullYear();
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    return yyyy + '-' + mm + '-' + dd;
  }

  function getYesterdayIso() {
    var d = new Date();
    d.setDate(d.getDate() - 1);
    var yyyy = d.getFullYear();
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    return yyyy + '-' + mm + '-' + dd;
  }

  function loadState() {
    var raw = null;
    try { raw = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    if (raw) {
      try {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') return parsed;
      } catch (e) {}
    }
    return {
      streak: 0,
      bestStreak: 0,
      lastActiveDate: null,
      mandiStreak: 0,
      lastMandiDate: null,
      mandiTotalChecks: 0,
      fasalLogs: 0,
      lastFasalDate: null,
      fasalStreak: 0,
      xp: 0,
      badges: {}
    };
  }

  function saveState(st) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(st));
    } catch (e) {}
  }

  function getLevel(xp) {
    var cur = LEVELS[0];
    for (var i = 0; i < LEVELS.length; i++) {
      if (xp >= LEVELS[i].minXp) cur = LEVELS[i];
    }
    var next = null;
    for (var j = 0; j < LEVELS.length; j++) {
      if (LEVELS[j].minXp > xp) {
        next = LEVELS[j];
        break;
      }
    }
    return {
      current: cur,
      next: next,
      progressPct: next ? Math.min(100, Math.round(((xp - cur.minXp) / (next.minXp - cur.minXp)) * 100)) : 100
    };
  }

  function unlockBadge(st, badgeKey) {
    var bDef = BADGES_DEF[badgeKey];
    if (!bDef) return null;
    if (!st.badges) st.badges = {};
    if (!st.badges[badgeKey]) {
      st.badges[badgeKey] = {
        unlocked: true,
        unlockedAt: new Date().toISOString()
      };
      st.xp = (st.xp || 0) + (bDef.xp || 10);
      saveState(st);
      return bDef;
    }
    return null;
  }

  function recordActivity(type, payload) {
    var st = loadState();
    var today = getTodayIso();
    var yesterday = getYesterdayIso();
    var newlyUnlocked = [];

    // General daily streak
    if (st.lastActiveDate !== today) {
      if (st.lastActiveDate === yesterday) {
        st.streak = (st.streak || 0) + 1;
      } else {
        st.streak = 1;
      }
      st.lastActiveDate = today;
      if (st.streak > (st.bestStreak || 0)) st.bestStreak = st.streak;
      st.xp = (st.xp || 0) + 10; // Daily checkin XP
    }

    if (type === 'mandi') {
      st.mandiTotalChecks = (st.mandiTotalChecks || 0) + 1;
      if (st.lastMandiDate !== today) {
        if (st.lastMandiDate === yesterday) {
          st.mandiStreak = (st.mandiStreak || 0) + 1;
        } else {
          st.mandiStreak = 1;
        }
        st.lastMandiDate = today;
      }
      // Check Mandi Milestones
      if (st.mandiTotalChecks >= 1) {
        var b1 = unlockBadge(st, 'mandi_1');
        if (b1) newlyUnlocked.push(b1);
      }
      if (st.mandiStreak >= 3) {
        var b3 = unlockBadge(st, 'mandi_3');
        if (b3) newlyUnlocked.push(b3);
      }
      if (st.mandiStreak >= 7) {
        var b7 = unlockBadge(st, 'mandi_7');
        if (b7) newlyUnlocked.push(b7);
      }
      if (st.mandiStreak >= 14) {
        var b14 = unlockBadge(st, 'mandi_14');
        if (b14) newlyUnlocked.push(b14);
      }
      if (st.mandiStreak >= 30) {
        var b30 = unlockBadge(st, 'mandi_30');
        if (b30) newlyUnlocked.push(b30);
      }
    } else if (type === 'fasal_add') {
      var bf1 = unlockBadge(st, 'fasal_1');
      if (bf1) newlyUnlocked.push(bf1);
    } else if (type === 'fasal_check') {
      st.fasalLogs = (st.fasalLogs || 0) + 1;
      if (st.lastFasalDate !== today) {
        if (st.lastFasalDate === yesterday) {
          st.fasalStreak = (st.fasalStreak || 0) + 1;
        } else {
          st.fasalStreak = 1;
        }
        st.lastFasalDate = today;
      }
      var bfl = unlockBadge(st, 'fasal_log');
      if (bfl) newlyUnlocked.push(bfl);
    } else if (type === 'calc') {
      var bc = unlockBadge(st, 'calc_1');
      if (bc) newlyUnlocked.push(bc);
    } else if (type === 'weather') {
      var bw = unlockBadge(st, 'weather_1');
      if (bw) newlyUnlocked.push(bw);
    } else if (type === 'news') {
      var bn = unlockBadge(st, 'news_reader');
      if (bn) newlyUnlocked.push(bn);
    }

    saveState(st);

    if (newlyUnlocked.length > 0) {
      newlyUnlocked.forEach(function (badge) {
        showCelebrationModal(badge, st);
      });
    }

    return st;
  }

  // ---- UI: Celebration Toast & Modal ----
  function injectGamifyStyles() {
    if (document.getElementById('km-gamify-styles')) return;
    var style = document.createElement('style');
    style.id = 'km-gamify-styles';
    style.textContent = [
      '/* KrashiMitra Gamification Styles */',
      '.km-cel-overlay{position:fixed;inset:0;background:rgba(15,23,20,0.65);backdrop-filter:blur(4px);z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px;animation:kmFadeIn .25s ease-out}',
      '.km-cel-modal{background:#ffffff;border-radius:20px;max-width:380px;width:100%;box-shadow:0 12px 40px rgba(0,0,0,0.25);overflow:hidden;border:2px solid #52b788;animation:kmPopIn .35s cubic-bezier(0.175,0.885,0.32,1.275);text-align:center;position:relative}',
      '.km-cel-confetti{background:linear-gradient(135deg,#1a3c2e 0%,#2d6a4f 100%);color:#fff;padding:24px 20px 16px;position:relative;overflow:hidden}',
      '.km-cel-badge-icon{width:72px;height:72px;border-radius:50%;background:#ffffff;box-shadow:0 6px 18px rgba(0,0,0,0.18);display:inline-flex;align-items:center;justify-content:center;font-size:38px;margin-bottom:10px;border:3px solid #e9a825}',
      '.km-cel-title{font-size:20px;font-weight:800;margin-bottom:4px;color:#ffffff;font-family:sans-serif}',
      '.km-cel-subtitle{font-size:13px;opacity:0.9;color:#d8f3dc}',
      '.km-cel-body{padding:20px;color:#1a2e1e}',
      '.km-cel-desc{font-size:14px;color:#334155;line-height:1.5;margin-bottom:14px}',
      '.km-cel-xp-pill{display:inline-flex;align-items:center;gap:6px;background:#fef3c7;border:1px solid #fde68a;color:#92400e;font-size:13px;font-weight:700;padding:5px 14px;border-radius:20px;margin-bottom:16px}',
      '.km-cel-actions{display:flex;flex-direction:column;gap:8px}',
      '.km-cel-btn-share{background:#25D366;color:#ffffff;border:none;border-radius:12px;padding:12px 16px;font-size:14px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;transition:opacity .15s}',
      '.km-cel-btn-share:hover{opacity:0.92}',
      '.km-cel-btn-close{background:#f1f5f9;color:#475569;border:none;border-radius:12px;padding:10px;font-size:13px;font-weight:700;cursor:pointer;transition:background .15s}',
      '.km-cel-btn-close:hover{background:#e2e8f0;color:#1e293b}',
      '@keyframes kmFadeIn{from{opacity:0}to{opacity:1}}',
      '@keyframes kmPopIn{from{transform:scale(0.85);opacity:0}to{transform:scale(1);opacity:1}}'
    ].join('\n');
    (document.head || document.documentElement).appendChild(style);
  }

  function showCelebrationModal(badge, st) {
    injectGamifyStyles();
    var overlay = document.createElement('div');
    overlay.className = 'km-cel-overlay';

    var shareText = '🎉 मुझे KrashiMitra पर "' + badge.title + '" बैज मिला! (' + badge.desc + ') 🌾🚜\n\nआप भी अपनी फसल का लाइव मंडी भाव व मौसम देखें: https://krashimitra.in/bhav';
    var waUrl = 'https://api.whatsapp.com/send?text=' + encodeURIComponent(shareText);

    overlay.innerHTML = [
      '<div class="km-cel-modal">',
        '<div class="km-cel-confetti">',
          '<div class="km-cel-badge-icon">' + badge.emoji + '</div>',
          '<div class="km-cel-title">बधाई! नया बैज अनलॉक 🏆</div>',
          '<div class="km-cel-subtitle">' + badge.title + '</div>',
        '</div>',
        '<div class="km-cel-body">',
          '<div class="km-cel-desc">' + badge.desc + '</div>',
          '<div class="km-cel-xp-pill">⚡ +' + (badge.xp || 20) + ' XP रिवॉर्ड हासिल हुआ</div>',
          '<div class="km-cel-actions">',
            '<a href="' + waUrl + '" target="_blank" rel="noopener" class="km-cel-btn-share">',
              '<span>📲</span> <span>व्हाट्सएप पर शेयर करें</span>',
            '</a>',
            '<button class="km-cel-btn-close" onclick="this.closest(\'.km-cel-overlay\').remove()">जारी रखें ✓</button>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) overlay.remove();
    });

    document.body.appendChild(overlay);
  }

  // Public API
  var KM_Gamify = {
    record: recordActivity,
    getState: loadState,
    getBadgesDef: function () { return BADGES_DEF; },
    getLevelsDef: function () { return LEVELS; },
    getLevelInfo: function () {
      var st = loadState();
      return getLevel(st.xp || 0);
    },
    shareBadge: function (badgeKey) {
      var b = BADGES_DEF[badgeKey];
      if (!b) return;
      var text = '🌾 मैंने KrashiMitra पर "' + b.title + '" बैज जीता! ' + b.desc + '\nरोज़ाना मंडी भाव व फसल सलाह के लिए: https://krashimitra.in/bhav';
      window.open('https://api.whatsapp.com/send?text=' + encodeURIComponent(text), '_blank');
    },
    renderStreakPill: function (containerEl) {
      if (!containerEl) return;
      var st = loadState();
      var streak = st.mandiStreak || st.streak || 0;
      var lvl = getLevel(st.xp || 0);
      containerEl.innerHTML = '<span style="display:inline-flex;align-items:center;gap:5px;background:#fef3c7;border:1px solid #fde68a;padding:4px 10px;border-radius:14px;font-size:12px;font-weight:700;color:#92400e;">' +
        '🔥 ' + streak + ' दिन स्ट्रीक · ' + lvl.current.emoji + ' ' + lvl.current.name_hi +
      '</span>';
    }
  };

  window.KrashiGamify = KM_Gamify;

  // Auto-detect page context
  document.addEventListener('DOMContentLoaded', function () {
    var p = window.location.pathname;
    if (/\/bhav(\/|$)/.test(p) || /krashi_bajar\.html/.test(p)) {
      KM_Gamify.record('mandi');
    } else if (/meri_fasal\.html/.test(p)) {
      KM_Gamify.record('fasal_check');
    } else if (/weather\.html/.test(p)) {
      KM_Gamify.record('weather');
    } else if (/krashi_news\.html/.test(p)) {
      KM_Gamify.record('news');
    }
  });

})(window, document);
