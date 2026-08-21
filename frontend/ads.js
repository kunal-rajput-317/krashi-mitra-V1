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

  var MIN_GAP = 700;    // px of real content required between two units
  var FOLD    = 1.05;   // first unit sits at least this × viewport down
  var MAX     = 3;      // never more than this many on one page
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
  // whole-segment, so /payment (if it ever exists) is unaffected.
  //
  // /map is deliberately NOT here, though it reads like one of the tools. It is
  // not a tool: naksha.py's up_map() renders it through the same _state_page()
  // as every other state, and /naksha/uttar-pradesh 301s into it. Listing it
  // meant the one state page every page's utility bar links to — Uttar Pradesh,
  // which also carries the cluster's search history — was the single state of
  // 36 that could not earn, while /naksha/bihar and the rest did.
  var OFF = /^\/(shop|login|profile|chat|cart|checkout|order|admin|404|khoj|krashi_bajar|meri_fasal|pay)(\.html)?(\/|$)/;

  // Blocks an ad must never be wedged into or placed directly before.
  var SKIP = '.answer,.hero,.crumbs,.km-ad,.ad-slot-wrap,.ad-slot-pair,.lead-gen,' +
             '.topbar-spacer,script,style,link,noscript,template,br,hr';
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
    '.km-ad ins[data-ad-status="unfilled"]{display:none!important}';

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
      if (st === 'unfilled') { settled = true; collapse(ins); return true; }
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
  function budget(height) {
    return height < 1400 ? 0 : height < 2600 ? 1 : height < 4200 ? 2 : MAX;
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

  function contentRoot() {
    return document.querySelector('[data-km-ads-root]') ||
           document.querySelector('.article-wrapper') ||
           document.querySelector('.wrap') ||
           document.querySelector('main') ||
           document.querySelector('article');
  }

  // Where the units already on the page sit — the anchors everything else has
  // to keep its distance from.
  function placedY() {
    return units.map(function (ins) { return topOf(ins); });
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
      if (units.length >= n || y < floor || y - last < MIN_GAP) {
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
    // A column flex container still stacks; anything else (grid, table, rows,
    // inline, list-item) does not, so leave it alone.
    return d.display.indexOf('flex') !== -1 && d.flexDirection.indexOf('column') === 0;
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
    gaps.push({ parent: root, before: null, y: topOf(root) + root.offsetHeight, brk: true });

    // Prefer section breaks (a heading) — an ad between two sections reads as a
    // divider; an ad between two paragraphs reads as an interruption.
    var breaks = gaps.filter(function (g) { return g.brk && g.y >= floor; });
    var pool = breaks.length >= n ? breaks : gaps.filter(function (g) { return g.y >= floor; });
    if (!pool.length) return;

    // The fold and the end of the content bracket the usable stretch; sitting
    // MIN_GAP outside it keeps a unit at either extreme legal.
    var bottom = topOf(root) + root.offsetHeight;
    var anchors = [floor - MIN_GAP, bottom + MIN_GAP].concat(placedY());

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
    // index/mandi/weather/sarkari_yojana were laid out deliberately.
    if (!marks.length && document.querySelector('ins.adsbygoogle')) return;

    var root = contentRoot();
    if (!root) return;

    var floor = floorY(window.innerHeight || 800);
    var n = budget(root.offsetHeight);
    if (!n) {
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
