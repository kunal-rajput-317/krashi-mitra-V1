// ============================================================
// KrashiMitra — phone fields: +91 by default, ten digits, escape hatch
//
// Mark any input with `data-km-tel` and this file turns it into the standard
// KrashiMitra phone control:
//
//   • a fixed **+91** sitting inside the field — the country code is furniture
//     here, not something a farmer should have to type;
//   • exactly ten digits, normalised as he types. Pasted and autofilled numbers
//     arrive as +91…, 91…, 0… or with spaces, so the country code and trunk
//     zero are peeled off rather than the tail truncated: a plain maxlength=10
//     turns "+919876543210" into "9198765432", a number that dials nobody;
//   • a "नंबर खुद लिखें" toggle. An STD landline, a second number, a
//     border-district code — all real, none of them ten Indian digits. The
//     strict box stays the default because it suits almost everyone; this is
//     the door for the rest, so an unusual number is typed as it is instead of
//     being quietly trimmed.
//
// The +91 is positioned *over* the field's own left padding instead of being a
// bordered box glued beside it, so the host page's border, radius, height and
// focus ring keep working untouched — this file makes no assumption about what
// an input looks like on the page that loads it.
//
// The /bhav appeal form carries its own inline twin of this logic (bhav.py's
// _APPEAL_JS): those pages are server-rendered and edge-cached, and the panel's
// script is a self-contained closure. Change one, change the other.
// ============================================================
(function () {
  'use strict';
  if (window.KMTel) return;

  /* Ten digits, +91 implied — the one shape a stored number takes. */
  function norm(raw) {
    var v = String(raw == null ? '' : raw).replace(/[^0-9]/g, '');
    if (v.length > 10 && v.slice(0, 2) === '91') v = v.slice(2);
    if (v.length > 10 && v.charAt(0) === '0') v = v.slice(1);
    return v.slice(0, 10);
  }

  var CSS = [
    '.km-tel{position:relative;display:block;width:100%}',
    '.km-tel-cc{position:absolute;left:12px;top:50%;transform:translateY(-50%);',
    'font-weight:700;color:#5c6f64;line-height:1;pointer-events:none;white-space:nowrap}',
    '.km-tel-cc::after{content:"";position:absolute;right:-7px;top:-6px;bottom:-6px;',
    'width:1px;background:currentColor;opacity:.28}',
    '.km-tel>input{padding-left:54px}',
    '.km-tel.km-free>.km-tel-cc{display:none}',
    '.km-tel.km-free>input{padding-left:12px}',
    '.km-tel-free{display:inline-block;margin-top:4px;background:none;border:0;padding:0;',
    'font:inherit;font-size:11px;font-weight:700;color:#2d6a4f;cursor:pointer;',
    'text-decoration:underline;text-align:left}',
    '.km-tel-free:hover{color:#1a3c2e}'
  ].join('');

  function injectCSS() {
    if (document.getElementById('km-tel-css')) return;
    var s = document.createElement('style');
    s.id = 'km-tel-css';
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  function upgrade(input) {
    if (!input || input.dataset.kmTelReady) return;
    input.dataset.kmTelReady = '1';

    var wrap = document.createElement('div');
    wrap.className = 'km-tel';
    input.parentNode.insertBefore(wrap, input);

    var cc = document.createElement('span');
    cc.className = 'km-tel-cc';
    cc.setAttribute('aria-hidden', 'true');
    cc.textContent = '+91';
    wrap.appendChild(cc);
    wrap.appendChild(input);

    var free = document.createElement('button');
    free.type = 'button';
    free.className = 'km-tel-free';
    wrap.parentNode.insertBefore(free, wrap.nextSibling);

    var strictHolder = input.getAttribute('placeholder') || '10 अंकों का नंबर';
    var freeHolder = input.getAttribute('data-km-tel-free') || 'जैसे 05522-234567';
    var isFree = false;

    function paint() {
      wrap.classList.toggle('km-free', isFree);
      /* 15, not 10, in strict mode: the browser applies maxlength to a paste
         before our handler ever sees it, so a pasted "+91 98765 43210" has to
         fit in the box long enough to be normalised. */
      input.maxLength = isFree ? 20 : 15;
      input.inputMode = isFree ? 'tel' : 'numeric';
      input.placeholder = isFree ? freeHolder : strictHolder;
      if (isFree) input.removeAttribute('pattern');
      else input.setAttribute('pattern', '[0-9]{10}');
      free.textContent = isFree
        ? '↩ +91 वाला 10 अंकों का डिब्बा'
        : 'दूसरा फ़ॉर्मैट — नंबर खुद लिखें';
    }

    free.addEventListener('click', function () {
      isFree = !isFree;
      /* Coming back to the strict box must leave a value it would accept. */
      if (!isFree) input.value = norm(input.value);
      paint();
      try { input.focus(); } catch (e) {}
    });

    input.addEventListener('input', function () {
      if (isFree) return;
      var pos = this.selectionStart, before = this.value, after = norm(before);
      if (after === before) return;
      this.value = after;
      /* Hold the caret where he was typing rather than throwing it to the end
         every time a stripped character shortens the value. */
      var back = Math.max(0, pos - (before.length - after.length));
      try { this.setSelectionRange(back, back); } catch (e) {}
    });

    /* A value put here by the page's own code (profile load, autofill) never
       fires `input`, so tidy it when he leaves the field. */
    input.addEventListener('change', function () {
      if (!isFree) this.value = norm(this.value);
    });

    if (input.value) input.value = norm(input.value);
    paint();
  }

  function scan(root) {
    var list = (root || document).querySelectorAll('input[data-km-tel]');
    for (var i = 0; i < list.length; i++) upgrade(list[i]);
  }

  function boot() { injectCSS(); scan(document); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.KMTel = { norm: norm, scan: scan, upgrade: upgrade };
})();
