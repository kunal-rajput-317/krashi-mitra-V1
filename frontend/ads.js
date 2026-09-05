// ============================================================
// KrashiMitra — automatic, content-aware AdSense placement
//
// Hand-placing ad units stopped scaling: /bhav alone is ~14k server-rendered
// pages, and of the 37 static articles 16 had units pasted in by hand, 4 had a
// loader and nothing else, and 17 had nothing at all. Every new article was one
// more file to remember. This script owns placement instead, so a page earns
// from the moment it ships — nothing to re-run, nothing to paste.
//
// It decides WHERE from the content itself, under rules that protect the reader:
//   • never above the fold, and never above the page's own call to action
//     (a quote lead or a WhatsApp share is worth far more than a click)
//   • at least MIN_GAP px of real content between two units, hard cap of 3,
//     scaled down on short pages and down to 1 on 2G / Save-Data phones
//   • units load lazily (IntersectionObserver), so the ad never competes with
//     the price table for a farmer's first bytes
//   • reserved height while loading, and the box collapses completely when
//     AdSense returns no ad, is blocked, or never answers — an empty slot
//     leaves no blank gap and no orphaned "विज्ञापन" label
//
// Three modes, picked automatically:
//   markers — page ships <div class="km-ad-slot"> placeholders (the converted
//             articles): fill those, keep the author's chosen positions
//   stand down — page already ships its own <ins class="adsbygoogle">
//             (index/mandi/weather/sarkari_yojana): touch nothing
//   auto    — everything else: place by the rules above
//
// Loaded on every page by drawer-menu.js (the one script the whole site shares)
// and explicitly by bhav.py's _doc() for cache-busting. Self-guards either way.
// ============================================================
(function () {
  if (window.__kmAdsInit) return;
  window.__kmAdsInit = 1;

  var PUB   = 'ca-pub-2792326360609634';
  var SLOT  = '7350859053';   // default in-content responsive unit
  var LABEL = 'विज्ञापन · Advertisement';

  // Lowered from 700 on request, to fit 4+ units on ordinary-length pages.
  // This is the number that decides how crowded the site feels: at 700 a page
  // needed ~3,000px of content below the fold to hold four units legitimately;
  // at 450 it needs ~1,800px. Raise it back first if the site starts reading
  // as an ad farm - it is the gentlest lever here, and the one that costs the
  // least revenue per unit of restraint.
  var MIN_GAP = 450;    // px of real content required between two units
  var FOLD    = 1.05;   // first unit sits at least this × viewport down
  var MAX     = 6;      // never more than this many on one page
  // Clear space required between a unit and the nearest CONTROL - a chip, a
  // pill, a button, a card people tap. Every other rule here spaces ads from
  // each other or from the fold; none of them knew where a thumb was going.
  // On 390px that is the whole ballgame: measured 5 Sept, a /krashi_news unit
  // sat 36px under the sub-filter pills, which is a miss away from a click
  // nobody meant. AdSense reads those as invalid traffic, and on 4 Sept it
  // limited the account for exactly that. Inline links inside prose are NOT
  // counted - a farmer reading a paragraph is not aiming at them; a row of
  // filter chips is where the thumb actually lands.
  var CLEAR   = 80;
  // The floor clearance never traded away, chosen from the measured spread
  // rather than picked. On /krashi_news the 20 candidate slots clear
  // 57/33x12/22/11/10/9/9/4/0/0 px: the twelve between-card slots all sit at
  // 33px because every card carries its own action button, and the genuinely
  // dangerous slots sit at 22 and below. /sarkari_yojana clusters the same way
  // at 27px. So 30 is the line that takes the card grids and refuses the rest.
  // At 45 a 7,131px page could seat one unit; at 30 it seats its full budget.
  //
  // 30px is not the separation a reader sees: .km-ad adds 26px of margin and a
  // 17px 'विज्ञापन' label above the slot, so the ad frame itself lands ~75px
  // below the button. Below 30 that stops being true - do not lower it.
  var CLEAR_MIN = 30;
  var GIVE_UP = 9000;   // ms before an unanswered slot collapses itself

  // Pages where an ad costs more than it earns: the quote flow (one lead beats
  // a thousand clicks), anything behind a login, and the interactive tools that
  // are apps rather than articles. /product/* is NOT here — those are Google
  // landing pages, and the quote form itself lives on shop.html.
  //
  // /pay is the strongest case of all: it is the one page where the site is
  // actually collecting money, so a competing ad is not a lost click, it is a
  // lost payment. A third-party ad next to a UPI amount also reads as exactly
  // the kind of page a farmer has been told to distrust. The segment match is
  // whole-segment, so /payment (if it ever exists) is unaffected. /donate is
  // here for exactly the same reason, from the other side: it is the page
  // asking a well-wisher for money, and an ad beside that ask both competes
  // with it and cheapens it.
  //
  // /dukanlisting is here for the same reason as the quote flow, and it is the
  // one entry whose cost is visible rather than theoretical. The page sells the
  // listing itself — a district a season at a time — so a dealer who finishes
  // the form is worth more than every ad impression the page will ever serve.
  // What forced it was desktop: the account has Auto ads on, and Auto ads'
  // anchor renders 1005x275 centred over the lower third of a 1366px window —
  // landing squarely on the login card and the plan tiles — while its in-page
  // unit is injected at the full body width, 1424px against this page's 760px
  // column. Neither is ours to place or to size: they arrive with the
  // adsbygoogle.js loader, and the only page-level switch for them is not
  // loading it. Dropping the ?client= from the loader does NOT help — measured
  // 2026-08-28, both units still appeared. On a phone the anchor is a thin bar,
  // which is why the page looked fine everywhere we normally check.
  //
  // /map is deliberately NOT here, though it reads like one of the tools. It is
  // not a tool: naksha.py's up_map() renders it through the same _state_page()
  // as every other state, and /naksha/uttar-pradesh 301s into it. Listing it
  // meant the one state page every page's utility bar links to — Uttar Pradesh,
  // which also carries the cluster's search history — was the single state of
  // 36 that could not earn, while /naksha/bihar and the rest did.
  var OFF = /^\/(shop|login|profile|chat|cart|checkout|order|admin|404|khoj|krashi_bajar|meri_fasal|pay|donate|dukanlisting)(\.html)?(\/|$)/;

  // Blocks an ad must never be wedged into or placed directly before.
  var SKIP = '.answer,.hero,.crumbs,.km-ad,.ad-slot-wrap,.ad-slot-pair,.lead-gen,' +
             '.topbar-spacer,script,style,link,noscript,template,br,hr,' +
             // The shared shell. These matter now that contentRoot() can fall
             // back to <body>: without them a page whose sections are direct
             // children of body could take a unit between the header and the
             // first section, or — worse — below the footer, where it is
             // rendered, requested, and never once seen.
             'header,footer,nav,.km-header,.km-footer,.site-footer,.bottomnav,.drawer';
  // A heading belongs to what follows it, so an ad never goes straight after one.
  var HEAD = 'h1,h2,h3';

  var STYLE_ID = 'km-ads-css';
  var CSS =
    '.km-ad{margin:26px auto 20px;text-align:center;overflow:hidden;max-width:100%}' +
    '.km-ad-lbl{display:block;font-family:inherit;font-size:11px;font-weight:600;' +
    'letter-spacing:.05em;text-transform:uppercase;color:#9aa8a0;margin-bottom:6px}' +
    '.km-ad ins.adsbygoogle{display:block;min-height:200px}' +
    '@media(min-width:768px){.km-ad ins.adsbygoogle{min-height:250px}}' +
    // In marker mode the article's own .ad-slot-wrap already supplies the
    // padding and the label, so our box must not stack a second set on top.
    '.km-ad-slot .km-ad{margin:0}' +
    // Belt-and-braces for the JS collapse below: an unfilled unit never leaves a gap.
    '.km-ad ins[data-ad-status^="unfill"]{display:none!important}';

  function css() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  // The AdSense loader goes in only once we know the page will actually show an
  // ad, so an ad-free page never pays for the script.
  function loader() {
    if (document.querySelector('script[src*="adsbygoogle.js"]')) return;
    var s = document.createElement('script');
    s.async = true;
    s.crossOrigin = 'anonymous';
    s.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' + PUB;
    (document.head || document.documentElement).appendChild(s);
  }

  function topOf(el) {
    return el.getBoundingClientRect().top + (window.pageYOffset || 0);
  }

  function build(opt) {
    var box = document.createElement('div');
    box.className = 'km-ad';
    // Harmless in normal flow, and required inside a grid: without it the box
    // becomes a grid item sized to one track instead of spanning the row.
    box.style.gridColumn = '1 / -1';
    if (opt.label !== false) {
      var lbl = document.createElement('span');
      lbl.className = 'km-ad-lbl';
      lbl.textContent = LABEL;
      box.appendChild(lbl);
    }
    var ins = document.createElement('ins');
    ins.className = 'adsbygoogle';
    ins.setAttribute('data-ad-client', PUB);
    ins.setAttribute('data-ad-slot', opt.slot || SLOT);
    ins.setAttribute('data-ad-format', opt.format || 'auto');
    if (opt.layout) ins.setAttribute('data-ad-layout-key', opt.layout);
    ins.setAttribute('data-full-width-responsive', 'true');
    box.appendChild(ins);
    return box;
  }

  // Hide the whole visual block, not just the <ins> — otherwise a converted
  // article is left showing a bare "विज्ञापन · Advertisement" label over nothing.
  function collapse(ins) {
    var box = ins.closest('.km-ad,.ad-slot-wrap,.ad-slot-pair') || ins.parentNode;
    if (box && box.style) box.style.display = 'none';
  }

  // AdSense answers asynchronously and sometimes not at all (no fill, an ad
  // blocker, localhost). Watch for the verdict, and time out into a collapse so
  // a dead slot can never leave a reserved-height hole in the page.
  function watch(ins) {
    var settled = false;
    function verdict() {
      var st = ins.getAttribute('data-ad-status');
      // Not just 'unfilled': AdSense also answers 'unfill-optimized' when it
      // declines to request the slot at all. Matching the exact string meant that
      // verdict fell through to the GIVE_UP timeout, which sees the stub iframe
      // AdSense leaves behind and therefore keeps the box — so a dead slot stood
      // for nine seconds as a ~350px hole under a live 'विज्ञापन' label.
      if (st && st.indexOf('unfill') === 0) { settled = true; collapse(ins); return true; }
      if (st === 'filled')   { settled = true; return true; }
      return false;
    }
    if (verdict()) return;
    var mo = new MutationObserver(function () { if (verdict()) mo.disconnect(); });
    mo.observe(ins, { attributes: true, attributeFilter: ['data-ad-status'] });
    setTimeout(function () {
      if (settled) return;
      mo.disconnect();
      if (!ins.querySelector('iframe')) collapse(ins);
    }, GIVE_UP);
  }

  // adsbygoogle.push() claims the earliest un-processed <ins> in the document,
  // not the one we happen to be looking at — so a reader who lands deep in the
  // page (an anchor link) would otherwise get unit #3's request wired to unit
  // #1's slot. Pushing everything up to the visible one keeps the mapping true.
  var units = [], pushed = 0;
  function pushTo(i) {
    loader();
    while (pushed <= i && pushed < units.length) {
      try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {}
      watch(units[pushed]);
      pushed++;
    }
  }

  function lazy() {
    if (!('IntersectionObserver' in window)) { pushTo(units.length - 1); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        pushTo(units.indexOf(e.target));
      });
      // 250% of the viewport ahead: the request is in flight well before the
      // unit is on screen, so the reader never watches an empty box fill in.
    }, { rootMargin: '250% 0px' });
    units.forEach(function (u) { io.observe(u); });
  }

  // How many units this page has earned. A short page gets none — three ads
  // around four paragraphs is what makes a site feel like a spam farm.
  // Thresholds are mobile heights, because 390px is where 98% of the readers
  // are and a phone page is naturally 2-3x the height of the same page on a
  // desktop. The old 1600/3600/6800 ladder was desktop-shaped: it gave a
  // 4,500px /bhav district page — a full price table, trend panel and FAQ —
  // only two units, and put the zero-unit cliff at 1600px, right in the middle
  // of where tier-1 and tier-2 crop pages actually land (measured: 1620-2776px).
  //
  // There is deliberately no navigator.connection cap here any more. It used to
  // drop a page to a single unit on saveData or a *2g effectiveType, which was
  // written as a courtesy to farmers on weak rural signal — but measurement
  // showed it firing on a real share of the audience (2 units -> 1) while being
  // invisible in DevTools, which reports 4g and Save-Data off. That is the
  // worst combination: a real revenue cost that no local test can reproduce.
  // The cost it was avoiding is small in any case, because units are lazy and
  // only request when they come near the viewport, and they are served from
  // Google's CDN rather than our own origin, so a slow phone pays for the ads
  // it actually reaches and nothing else.
  // The old ladder topped out at 3 units and then stopped caring how long a
  // page was, so /krashi_news at 25,320px earned exactly what a 4,200px article
  // did. Above the old ceiling this keeps roughly one unit per 4,000px, which
  // MIN_GAP (700px of real content between units) would permit many times over
  // - the spacing rules, not this number, are what actually protect the reader.
  // The zero-cliff stays at 1400px: three ads around four paragraphs is what
  // makes a site feel like a spam farm, and that has not changed.
  // Raised on request: at least 4 units on any page long enough to seat them,
  // 5-6 on the long ones. The floor stays a hard 0 under 1,200px because four
  // ads around three paragraphs is not a denser page, it is a worse one - and
  // MIN_GAP would refuse to place them anyway.
  //
  // These are ceilings, not quotas. spread() still refuses any position closer
  // than MIN_GAP to another unit, and clearOfTaps() still refuses one that
  // crowds a control, so a page that cannot seat its budget safely simply
  // places fewer. That is deliberate: the number below says how many are
  // ALLOWED, and the geometry decides how many are EARNED.
  function budget(height) {
    return height <  1200 ? 0
         : height <  1800 ? 2
         : height <  2600 ? 3
         : height <  4000 ? 4
         : height <  7000 ? 5
         : MAX;
  }

  // An ad must never sit above the page's own conversion point. Only CTAs near
  // the top count as "the" CTA — /bhav repeats a WhatsApp share button at the
  // very bottom, and that one must not veto every mid-content placement.
  function ctaFloor(vh) {
    var y = 0;
    [].forEach.call(
      document.querySelectorAll('.answer,.hero,.cta-row,.answer-actions,.hub-filter-row'),
      function (el) {
        var t = topOf(el);
        if (t > vh * 1.5) return;
        var b = t + el.offsetHeight;
        if (b > y) y = b;
      });
    return y;
  }

  // No unit may sit above this line, whichever mode placed it.
  function floorY(vh) {
    return Math.max(vh * FOLD, ctaFloor(vh) + 120);
  }

  function hide(el) { if (el && el.style) el.style.display = 'none'; }

  // Chunky, deliberately-tapped things. A 32px minimum height is what separates
  // a filter chip or a card from an <a> in the middle of a sentence.
  var TAPPY = 'button,[role=button],input,select,summary,.btn,.news-action-btn,' +
              '.sub-pill,.topic-card,.faq-q,.ccard-btn,.cnav-item,.km-bn-item';

  // Size is what makes a control dangerous, and the danger is SMALLNESS. A row
  // of filter chips is a thumb-sized target in a dense row, and a miss lands
  // on whatever is next to it. A 427px article card is an enormous unambiguous
  // target that nobody misses - and treating cards as hazards was measurably
  // wrong: at CLEAR=110 counting every card link, /krashi_news (221 tappables,
  // 7,588px) placed zero units, which trades a real revenue loss for a risk
  // that was not there. So: only controls between 20 and 72px tall count.
  var TAP_MIN = 20, TAP_MAX = 72;

  var _taps = null;
  function tapBands() {
    if (_taps) return _taps;
    _taps = [];
    [].forEach.call(document.querySelectorAll(TAPPY + ',a'), function (el) {
      var h = el.offsetHeight;
      if (h < TAP_MIN || h > TAP_MAX) return;
      // Prose links are noise - a reader is not aiming at them.
      if (el.tagName === 'A' && !el.matches(TAPPY) && h < 32) return;
      if (el.closest('header,footer,nav,.km-footer,.site-footer,.bottomnav')) return;
      var t = topOf(el);
      _taps.push([t, t + h]);
    });
    return _taps;
  }

  // How far y sits from the nearest control, in either direction.
  function clearOfTaps(y) {
    var best = Infinity;
    var bands = tapBands();
    for (var i = 0; i < bands.length; i++) {
      var d = y < bands[i][0] ? bands[i][0] - y
            : y > bands[i][1] ? y - bands[i][1] : 0;
      if (d < best) best = d;
      if (!best) break;
    }
    return best;
  }

  // Which selector matches is a far weaker signal than how tall the match is,
  // and the old first-match-wins chain got both halves wrong. Measured at 390px
  // on 2026-09-05:
  //
  //   terms.html (5,192px), privacy-policy.html (9,479px), np.html (6,527px)
  //     match NONE of the selectors — their content sits in .main-content — so
  //     contentRoot() returned null and init() exited. Zero ads, permanently.
  //   help.html (4,756px) has three sibling .wrap sections; querySelector took
  //     the first (1,383px), which the budget ladder rounds down to zero ads.
  //   krashi_news.html matches `article` seventeen times, every one of them a
  //     427px card, against the 7,653px <main> that holds them all.
  //
  // So: an explicit opt-in always wins, otherwise take the TALLEST candidate,
  // and if nothing plausible matches, look for the tallest block container on
  // the page before giving up on <body>. Anything containing the shared header
  // or footer is not a content root, it is the page.
  function chrome(el) {
    return !!el.querySelector('header,footer,.km-footer,.site-footer,.bottomnav');
  }

  function tallest(list) {
    var best = null;
    [].forEach.call(list, function (el) {
      if (!el.offsetHeight || chrome(el)) return;
      if (!best || el.offsetHeight > best.offsetHeight) best = el;
    });
    return best;
  }

  function contentRoot() {
    var explicit = document.querySelector('[data-km-ads-root]');
    if (explicit) return explicit;

    var best = tallest(document.querySelectorAll(
      '.article-wrapper,main,.main-content,.page-container,.wrap,article'));
    if (best && best.offsetHeight >= 1400) return best;

    // Nothing named the content, so find it by shape: the tallest vertical
    // stack that is not the page chrome. Keeps the never-null contract that
    // <body> alone would give while still preferring a real container.
    var shaped = tallest([].filter.call(
      document.body.querySelectorAll('div,section'),
      function (el) { return el.children.length > 1 && el.offsetHeight > 1400; }));
    var root = shaped || best;

    // A root far shorter than the page means the content is not in one box at
    // all: help.html stacks three sibling .wrap sections of 1,383/1,173/951px
    // across a 4,756px document, so the tallest single container is under the
    // zero-ad cliff while the page itself is comfortably a two-unit page.
    // Falling back to <body> measures and uses the whole stack. That is only
    // safe because SKIP now excludes the header, footer and bottom nav.
    if (!root || root.offsetHeight < document.body.scrollHeight * 0.55) {
      return document.body;
    }
    return root;
  }

  // Where the units already on the page sit — the anchors everything else has
  // to keep its distance from.
  function placedY() {
    var ys = units.map(function (ins) { return topOf(ins); });
    // Hand-placed units are anchors we never touch but must never crowd.
    [].forEach.call(document.querySelectorAll('ins.adsbygoogle[data-km-ad="page"]'),
      function (ins) { ys.push(topOf(ins)); });
    return ys;
  }

  // Choose positions that sit as far as possible from everything already
  // placed. With the fold and the end of the article as fixed anchors, each
  // pick lands in the middle of the biggest remaining stretch of content: that
  // spreads units evenly on a bare page, and fills the gaps a rejected marker
  // left behind. Greedy-from-the-top instead piles every ad into the opening
  // third and leaves the rest of a 12,000px article bare.
  function spread(pool, anchors, want) {
    var picked = [];
    while (picked.length < want) {
      var best = null, bestD = 0;
      for (var i = 0; i < pool.length; i++) {
        var g = pool[i];
        if (g.used) continue;
        var d = Infinity;
        for (var j = 0; j < anchors.length; j++) {
          d = Math.min(d, Math.abs(g.y - anchors[j]));
        }
        if (d > bestD) { bestD = d; best = g; }
      }
      if (!best || bestD < MIN_GAP) break;
      best.used = 1;
      anchors.push(best.y);
      picked.push(best);
    }
    return picked.sort(function (a, b) { return a.y - b.y; });
  }

  // ---- mode: fill the <div class="km-ad-slot"> markers a page ships ----
  // The marker positions are the article author's, but the rules are still
  // ours: a marker that sits above the fold, crowds the one before it, or
  // exceeds the page's budget stays empty and its wrapper is removed. Anything
  // dropped here is made back by autoMode, which runs afterwards on the hole.
  function markerMode(marks, n, floor) {
    var last = floor - MIN_GAP;
    marks.forEach(function (m) {
      var y = topOf(m);
      if (units.length >= n || y < floor || y - last < MIN_GAP ||
          clearOfTaps(y) < CLEAR_MIN) {
        hide(m.closest('.ad-slot-wrap,.ad-slot-pair') || m);
        return;
      }
      last = y;
      // The converted articles keep their own .ad-slot-label, so no second one.
      var box = build({
        slot:   m.getAttribute('data-slot'),
        format: m.getAttribute('data-format'),
        layout: m.getAttribute('data-layout'),
        label:  m.hasAttribute('data-label')
      });
      m.appendChild(box);
      units.push(box.querySelector('ins'));
    });
  }

  // A box can only be dropped between children that stack vertically. Splitting
  // a grid or a flex row would shove a card onto its own line and wreck the
  // layout — /bhav's crop tiles and district links are both grids.
  // Elements whose children may not legally be interrupted by a <div>, however
  // they happen to be styled.
  var CLOSED = /^(UL|OL|DL|TABLE|THEAD|TBODY|TFOOT|TR|SELECT|PICTURE|FIGURE)$/;

  function splittable(el) {
    if (CLOSED.test(el.tagName)) return false;
    var d = getComputedStyle(el);
    if (d.display === 'block' || d.display === 'flow-root') return true;
    // A column flex container still stacks.
    if (d.display.indexOf('flex') !== -1) return d.flexDirection.indexOf('column') === 0;
    // A grid stacks too when it has resolved to a SINGLE column - which is what
    // every card grid on this site does at 390px, where 98% of the readers are.
    // Refusing all grids outright was the single biggest cause of missing
    // inventory: /krashi_news holds its 12 story cards in a 5,299px .cards-grid
    // and /sarkari_yojana holds 14 in a 4,298px one, and both offered ads.js
    // exactly zero places to put anything. Multi-column grids are still off
    // limits - dropping a full-width box into one shoves a card onto its own
    // row and wrecks the layout.
    // Any grid is fine, one column or several, because build() gives the box
    // grid-column: 1 / -1 - it becomes its own full-width row and the cards
    // reflow around it instead of one being shoved onto a line of its own.
    // That is what the original "never split a grid" rule was protecting
    // against, and spanning the row removes the danger entirely.
    //
    // A wrapping flex ROW is still off limits and always will be: it has no
    // equivalent of grid-column, so a block dropped into one breaks the wrap.
    // /bhav's .chips is exactly that - 280 chips over 5,992px - and it is the
    // last place an ad belongs anyway, being a dense field of small tap targets.
    if (d.display.indexOf('grid') !== -1) return true;
    return false;
  }

  // Most of a page's content usually lives inside one tall wrapper — /bhav's
  // .bhav-pane holds 8,000 of the hub's 8,900px — so the root's own children
  // offer almost nowhere to put anything. Descend into tall block containers to
  // find real gaps, stopping at anything that isn't a vertical stack.
  function collect(box, depth, out) {
    var kids = [].slice.call(box.children);
    for (var i = 0; i < kids.length; i++) {
      var el = kids[i], prev = kids[i - 1];
      if (!el.matches || el.matches(SKIP) || !el.offsetHeight) continue;
      // i === 0 is either the top of the page or a duplicate of the gap already
      // recorded before this container.
      if (i > 0 && !prev.matches(HEAD) && !prev.matches('.lead-gen')) {
        out.push({ parent: box, before: el, y: topOf(el),
                   brk: el.matches(HEAD) || !!el.querySelector('h2,h3') });
      }
      if (depth < 2 && el.offsetHeight > 1500 && el.children.length > 1 && splittable(el)) {
        collect(el, depth + 1, out);
      }
    }
  }

  // ---- mode: choose the positions ourselves ----
  function autoMode(root, n, floor) {
    var gaps = [];
    if (splittable(root)) collect(root, 0, gaps);

    // Where the content actually ends. Appending to the root was fine while the
    // root was always an article wrapper, but the root can now be <body>, whose
    // last children are the footer and the bottom nav — a unit appended there
    // renders, requests, and sits below everything a reader will ever scroll
    // to. Anchor to the last real child instead and insert before whatever
    // chrome follows it.
    var kids = [].slice.call(root.children), tail = null;
    for (var i = kids.length - 1; i >= 0; i--) {
      var k = kids[i];
      if (k.matches && !k.matches(SKIP) && k.offsetHeight) { tail = k; break; }
    }
    var endY = tail ? topOf(tail) + tail.offsetHeight
                    : topOf(root) + root.offsetHeight;
    gaps.push({ parent: root, before: tail ? tail.nextElementSibling : null,
                y: endY, brk: true });

    // Prefer section breaks (a heading) — an ad between two sections reads as a
    // divider; an ad between two paragraphs reads as an interruption.
    // Clearance is applied before the fold/heading preference, so a page never
    // trades a safe position for a prettier one.
    var safe = gaps.filter(function (g) { return clearOfTaps(g.y) >= CLEAR; });
    if (safe.length < n) {
      // Nothing comfortable: take whatever clears the hard floor, roomiest
      // first, so the page still earns and still puts the ad in the safest
      // place that exists on it.
      // Keep EVERY position that clears the floor, in document order. Sorting
      // by roominess and slicing looked smarter and was measurably worse: the
      // roomiest positions on /krashi_news all sit in the same sparse stretch,
      // so spread() ran out of candidates that were MIN_GAP apart and placed a
      // single unit on a 7,835px page. spread() already maximises distance
      // from what is placed - it needs breadth of choice, not a shortlist.
      safe = gaps.filter(function (g) { return clearOfTaps(g.y) >= CLEAR_MIN; });
    }
    var breaks = safe.filter(function (g) { return g.brk && g.y >= floor; });
    var pool = breaks.length >= n ? breaks
             : safe.filter(function (g) { return g.y >= floor; });
    if (!pool.length) return;

    // The fold and the end of the content bracket the usable stretch; sitting
    // MIN_GAP outside it keeps a unit at either extreme legal.
    var anchors = [floor - MIN_GAP, endY + MIN_GAP].concat(placedY());

    // Placement is geometry, and geometry is invisible in a bug report. This
    // records what the page offered and what survived each rule, so an audit
    // can tell "no room" apart from "a rule rejected everything" without
    // rebuilding the algorithm in the probe. Costs one object per pageview.
    window.__kmAdsDbg = {
      rootH: root.offsetHeight, want: n, gaps: gaps.length,
      clear: safe.length, breaks: breaks.length, pool: pool.length, floor: floor
    };

    spread(pool, anchors, n).forEach(function (g) {
      var box = build({});
      if (g.before) g.parent.insertBefore(box, g.before); else g.parent.appendChild(box);
      units.push(box.querySelector('ins'));
    });
  }

  function init() {
    if (OFF.test(location.pathname)) return;
    if (document.body.getAttribute('data-km-ads') === 'off') return;

    var marks = [].slice.call(document.querySelectorAll('.km-ad-slot'));
    // A page that already hand-places its own units keeps its own layout —
    // index/weather/sarkari_yojana were laid out deliberately.
    //
    // The test is data-km-ad="page", NOT a bare ins.adsbygoogle, and that
    // distinction is the whole point. init() runs at load + a settle loop, by
    // which time Auto ads has usually injected <ins class="adsbygoogle"> of its
    // own — so the bare test read Google's injected markup as "this page places
    // its own ads" and stood down. Measured on the live site 2026-09-05, at
    // 390px, after a full scroll: /krashi_news is a 25,320px document, easily
    // MAX budget, and carried ZERO ads.js units; the /bhav hub placed only 2,
    // both inside a clipped container. That is the missing coverage behind the
    // site-wide 1.06 ads per pageview when the budget ladder should be giving
    // 2-3. It is also a race — /bhav won it, /krashi_news lost it — which is
    // why the shortfall looked random rather than broken.
    //
    // An authored unit is one WE wrote into the HTML, so it can say so. Nothing
    // Google injects at runtime carries this attribute, so Auto ads can never
    // silence this script again, whatever the account setting is doing.
    // Hand-placed units keep their positions, but a page no longer stops
    // earning just because someone once put two units on it. index.html is
    // 8,585px and shipped 2; weather.html is 1,919px and shipped 2. The
    // authored units are treated as fixed anchors and the remaining budget is
    // filled around them, MIN_GAP away, under the same clearance rules.
    //
    // They are anchors, never managed units: each one carries its own
    // adsbygoogle.push() in the page, so pushing them again here would request
    // the same slot twice.
    var authored = [].slice.call(
      document.querySelectorAll('ins.adsbygoogle[data-km-ad="page"]'));

    var root = contentRoot();
    if (!root) return;

    var floor = floorY(window.innerHeight || 800);
    var n = budget(root.offsetHeight) - authored.length;
    if (n <= 0) {
      marks.forEach(function (m) { hide(m.closest('.ad-slot-wrap,.ad-slot-pair') || m); });
      return;
    }

    css();
    if (marks.length) markerMode(marks, n, floor);
    // Markers the rules rejected are re-earned here: autoMode measures the page
    // as it now stands and drops the remaining budget into the largest holes.
    if (units.length < n) autoMode(root, n - units.length, floor);
    if (!units.length) return;

    // adsbygoogle claims <ins> elements in document order, so our queue has to
    // be in document order too. The two modes append in placement order, and a
    // top-up unit can land above units that were created before it.
    units.sort(function (a, b) {
      return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1;
    });
    loader();   // warm the script now that we know this page will show an ad
    lazy();
  }

  // Placement measures real geometry, so it waits for layout — fonts and images
  // change every offsetHeight this script reads.
  //
  // 'load' is necessary but not sufficient on /bhav: the location card and the
  // nearest-mandi panel are injected by their own scripts after it fires, and
  // lazy images resolve later still. Measuring once at 'load' read the page
  // mid-growth, and since tier-1/tier-2 pages sit within a few hundred px of
  // the zero-unit cliff, the SAME url placed 0 units on one visit and 1 on the
  // next — coverage that looked random rather than broken. Wait for two
  // consecutive equal heights (capped, so a page that never settles still gets
  // its ads) and every visit measures the same page.
  function boot() {
    function start() {
      var root = contentRoot();
      if (!root) { init(); return; }
      var last = -1, tries = 0;
      (function settle() {
        var h = root.offsetHeight;
        if (h === last || ++tries > 12) { init(); return; }
        last = h;
        setTimeout(settle, 120);
      })();
    }
    if (document.readyState === 'complete') { start(); return; }
    window.addEventListener('load', start, { once: true });
  }
  boot();
})();
