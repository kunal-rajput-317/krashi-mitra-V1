/* ============================================================
   km-mandi-memory.js — "आपकी मंडी" recall + "पिछली बार से" change
   ------------------------------------------------------------
   A /bhav page answers the farmer's question completely and then has nothing
   left to say, which is why ~200 new visitors a day produced 10-20 returning
   ones. Every farmer who came back saw the identical page a stranger sees.

   This remembers the crop+mandi he last looked at (no login, no permission
   dialog, no account) and gives a return visit two things a first visit cannot
   have: a one-tap route back to his own mandi, and what the price has done
   since he last looked.

   ── THE CORRECTNESS RULES ───────────────────────────────────
   A remembered price is the easiest way to tell a farmer something false, so:

   1. A stored price is NEVER redisplayed as if it were current. It appears
      only inside a "पिछली बार … था" sentence, always carrying its own date.
   2. The recall band fetches the live number from /bhav/api/quote. If that
      fetch fails the band renders as a plain link with NO figure — never the
      remembered one.
   3. A change is only claimed when the market actually reported again, i.e.
      the page's data date is NEWER than the stored one. Two visits against the
      same report produce no claim at all — not "कोई बदलाव नहीं", because about
      half of all mandi×crop pairs are carried forward on any given day and the
      price may well have moved without being reported. "No new report" and
      "no change" are different facts and only one of them is ours to state.
   4. Every stored price is shown with the day it was reported, never the day
      the farmer happened to visit.

   Storage is localStorage: per-browser, invisible to us, and every access is
   wrapped because it throws in private mode and can come back empty.
   ============================================================ */
(function () {
  'use strict';

  var KEY = 'km_mandi_memory';
  var V = 1;
  // Past this, a comparison stops being useful to a farmer even though the
  // arithmetic is still true — he is not deciding today against a price from
  // two months ago. The remembered PLACE is kept regardless; only the number
  // is retired, so the recall band goes on working.
  var MAX_COMPARE_DAYS = 60;

  var HI_MONTHS = ['जनवरी', 'फ़रवरी', 'मार्च', 'अप्रैल', 'मई', 'जून',
                   'जुलाई', 'अगस्त', 'सितंबर', 'अक्टूबर', 'नवंबर', 'दिसंबर'];

  function track(name, params) {
    try { if (window.kmTrack) window.kmTrack(name, params || {}); } catch (e) {}
  }

  function read() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return null;
      var m = JSON.parse(raw);
      return (m && m.v === V && m.crop) ? m : null;
    } catch (e) { return null; }
  }

  function write(m) {
    try { localStorage.setItem(KEY, JSON.stringify(m)); } catch (e) {}
  }

  /* '2026-09-19' → '19 सितंबर'. Returns '' for anything it cannot parse, and
     every caller treats '' as "say nothing about when". */
  function hiDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    if (!m) return '';
    var mon = parseInt(m[2], 10);
    if (mon < 1 || mon > 12) return '';
    return parseInt(m[3], 10) + ' ' + HI_MONTHS[mon - 1];
  }

  function daysBetween(isoA, isoB) {
    var a = Date.parse(isoA + 'T00:00:00Z'), b = Date.parse(isoB + 'T00:00:00Z');
    if (isNaN(a) || isNaN(b)) return null;
    return Math.round((b - a) / 86400000);
  }

  function rupee(n) {
    try { return '₹' + Number(n).toLocaleString('en-IN'); }
    catch (e) { return '₹' + n; }
  }

  /* The page's own identity and today's figure, server-rendered. Absent on
     tier-2/3 pages, which have no single mandi price to remember. */
  function pageCtx() {
    var el = document.getElementById('km-mandi-ctx');
    if (!el) return null;
    try {
      var c = JSON.parse(el.textContent || '{}');
      return (c && c.crop && c.price) ? c : null;
    } catch (e) { return null; }
  }

  function sameMandi(a, b) {
    return a && b && a.crop === b.crop && a.state === b.state
        && a.district === b.district;
  }

  // ── #2 — what the price has done since he last looked ──────
  function renderDelta(mem, ctx) {
    // Rule 3: no new report, no claim.
    if (!mem.price || !mem.date || !ctx.date) return;
    if (!(ctx.date > mem.date)) return;

    var gap = daysBetween(mem.date, ctx.date);
    if (gap === null || gap > MAX_COMPARE_DAYS) return;

    var diff = ctx.price - mem.price;
    var when = hiDate(mem.date);
    if (!when) return;                       // rule 4: no date, no sentence

    // kmd- prefixed, never a bare `up`/`dn`: /bhav's stylesheet carries a global
    // .up/.dn pair for its light price cards, and inheriting it here paints the
    // band's text dark green on a dark photo.
    var cls, arrow, tail;
    if (diff > 0) {
      cls = 'kmd-up'; arrow = '▲';
      tail = '<b>' + rupee(diff) + ' ज़्यादा</b> है';
    } else if (diff < 0) {
      cls = 'kmd-dn'; arrow = '▼';
      tail = '<b>' + rupee(-diff) + ' कम</b> है';
    } else {
      cls = 'kmd-same'; arrow = '•';
      tail = '<b>वही</b> है';
    }

    var host = document.querySelector('.answer-in');
    var before = document.querySelector('.answer-range');
    if (!host) return;

    var d = document.createElement('div');
    d.className = 'km-memo-delta ' + cls;
    d.setAttribute('role', 'status');
    d.innerHTML =
      '<span class="kmd-ic" aria-hidden="true">' + arrow + '</span>' +
      '<span class="kmd-t">पिछली बार आपने <b>' + rupee(mem.price) + '</b> देखा था (' +
      when + ') — आज का भाव ' + tail + '</span>';
    if (before && before.parentNode === host) host.insertBefore(d, before);
    else host.appendChild(d);

    track('bhav_memo_delta_shown', {
      crop: ctx.crop, district: ctx.district,
      direction: diff > 0 ? 'up' : (diff < 0 ? 'down' : 'flat'),
      gap_days: gap
    });
  }

  // ── #1 — "आपकी मंडी", on a page that is not it ─────────────
  function renderRecall(mem) {
    var host = document.querySelector('section.answer');
    var main = document.querySelector('main') || document.body;

    var box = document.createElement('div');
    box.className = 'km-memo-recall km-memo-loading';
    var label = (mem.cropHi || mem.crop) + ' · ' + (mem.placeHi || mem.district || mem.state || '');
    box.innerHTML =
      '<a class="kmr-go" href="' + mem.url + '">' +
        '<span class="kmr-ic" aria-hidden="true">📍</span>' +
        '<span class="kmr-txt"><b>आपकी मंडी</b><span class="kmr-sub">' + label + '</span></span>' +
        '<span class="kmr-price" aria-live="polite"></span>' +
        '<span class="kmr-arrow" aria-hidden="true">›</span>' +
      '</a>';

    // After the answer the farmer actually came for — never above it. On a hub
    // page (no answer section) it goes to the top, where it is the fastest
    // route out.
    if (host && host.parentNode) host.parentNode.insertBefore(box, host.nextSibling);
    else main.insertBefore(box, main.firstChild);

    box.querySelector('.kmr-go').addEventListener('click', function () {
      track('bhav_memo_recall_click', { crop: mem.crop, district: mem.district });
    });
    track('bhav_memo_recall_shown', { crop: mem.crop, district: mem.district });

    // Rule 2: the number comes from the server or not at all.
    var q = '/bhav/api/quote?crop=' + encodeURIComponent(mem.crop) +
            '&state=' + encodeURIComponent(mem.state || '') +
            '&district=' + encodeURIComponent(mem.district || '');
    fetch(q).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      box.classList.remove('km-memo-loading');
      if (!j || !j.ok || !j.avg) return;     // link only, no figure
      var when = hiDate(j.date);
      var slot = box.querySelector('.kmr-price');
      slot.innerHTML = '<b>' + rupee(j.avg) + '</b>' +
                       (when ? '<small>' + when + '</small>' : '');
      // Keep the remembered labels current with what the server calls them.
      if (j.crop_hi)  mem.cropHi  = j.crop_hi;
      if (j.place_hi) mem.placeHi = j.place_hi;
      write(mem);
    }).catch(function () {
      box.classList.remove('km-memo-loading');
    });
  }

  function run() {
    var ctx = pageCtx();
    var mem = read();

    if (ctx) {
      if (sameMandi(mem, ctx)) renderDelta(mem, ctx);
      else if (mem) renderRecall(mem);

      // Remember what he is looking at NOW — after the delta, which needs the
      // previous value. Stored with the date the market reported, never the
      // date of the visit.
      write({
        v: V, crop: ctx.crop, state: ctx.state, district: ctx.district,
        cropHi: ctx.cropHi, placeHi: ctx.placeHi, url: ctx.url,
        price: ctx.price, date: ctx.date, seenAt: Date.now()
      });
      track('bhav_memo_saved', { crop: ctx.crop, district: ctx.district });
      return;
    }

    if (mem) renderRecall(mem);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
