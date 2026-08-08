// ============================================================
// frontend/dukan-promo.js
// The "list your shop on the bhav pages" promo, in one place.
//
// Most visitors have never heard of this feature, so the block has to teach
// it rather than just price it: who it is for, what it looks like, what it
// costs, one button. The sample product card is the load-bearing part — it is
// the actual thing being sold, so showing one beats any sentence describing it.
//
// A page opts in with a single placeholder:
//     <div data-dukan-promo></div>
//
// Markup AND styles ship together from this file. They used to live in
// km-shell.css, which the two pages that actually opt in (index.html,
// krashi_bajar.html) do not load — they predate the shared shell and carry
// their own chrome — so the block rendered as unstyled text. Pulling km-shell
// into them to fix one card would have restyled their headers and footers too.
// Self-contained is the smaller change, and it means any future page opts in
// with the placeholder alone.
//
// backend/routes/bhav.py::_dukan_pitch() + its _DKP_CSS are the server twin for
// the ~10,000 SEO pages — same classes, same layout, same copy. Change one,
// change the other.
//
// Same "one edit, every page" reasoning as drawer-menu.js: the alternative is
// this markup copy-pasted into 40-odd static files, where it drifts the first
// time the price changes.
// ============================================================
(function () {
  // The sample card's photo — a real photograph, not the drawn bag that was
  // here before: the block's whole claim is "your product will look like
  // this", and a cartoon undersells the thing being sold. Root-relative so it
  // resolves from a nested page too, and deliberately an unbranded pack: this
  // is our sample printed next to a price we invented.
  //
  // 240px square, ~15 KB, rendered at 72–100px. Keep it in step with
  // backend/routes/bhav.py::_PACK_IMG.
  var PACK_IMG =
    '<img src="/images/seeds/wheat-seed-hd2967-card.webp" ' +
    'alt="नमूना प्रोडक्ट फोटो — गेहूं बीज" ' +
    'width="240" height="240" loading="lazy" decoding="async">';

  // 98% of this site's traffic is a phone, so the phone layout is the real
  // one: the sample card floats as a thumbnail and the copy wraps around it,
  // which keeps the whole block around a third of a screen. The two-column
  // desktop version below is the variant.
  var CSS =
    '.kmdp{max-width:1000px;margin:22px auto;padding:16px;box-sizing:border-box;' +
      'background:linear-gradient(135deg,#fffdf6 0%,#fdf6e3 100%);' +
      'border:1px solid #f0dfae;border-radius:14px;' +
      'box-shadow:0 2px 14px rgba(120,95,20,.07);' +
      "font-family:var(--km-font-body,'DM Sans',sans-serif)}" +
    '.kmdp-eyebrow{display:inline-flex;align-items:center;gap:6px;margin-bottom:8px;' +
      'background:rgba(233,168,37,.18);border:1px solid rgba(233,168,37,.42);' +
      'color:#7a5200;font-size:11px;font-weight:800;padding:3px 10px;border-radius:20px}' +
    // Phone: the card floats right, the text runs beside and then under it.
    '.kmdp-demo{float:right;width:104px;margin:0 0 10px 12px;text-align:center}' +
    '.kmdp-h{font-family:var(--km-font-serif,serif);font-size:16px;font-weight:800;' +
      'line-height:1.35;color:var(--km-green-dark,#1a3c2e);margin:0 0 5px}' +
    '.kmdp-p{font-size:12.5px;line-height:1.55;color:#5b4a1e;margin:0 0 9px}' +
    '.kmdp-list{list-style:none;padding:0;margin:0 0 12px;display:grid;gap:5px}' +
    // The ✓ is positioned, not a flex item: as flex, the <b> lead and the rest
    // of the sentence became two columns and every line broke mid-phrase.
    '.kmdp-list li{position:relative;padding-left:23px;' +
      'font-size:12px;line-height:1.45;color:#3d4a43}' +
    ".kmdp-list li::before{content:'✓';position:absolute;left:0;top:1px;" +
      'width:16px;height:16px;border-radius:50%;' +
      'background:var(--km-green-mid,#2d6a4f);color:#fff;font-size:9.5px;font-weight:800;' +
      'display:flex;align-items:center;justify-content:center}' +
    '.kmdp-list b{color:var(--km-green-dark,#1a3c2e);font-weight:700}' +
    // clear:both so the button never tucks into the float and lose half its width.
    '.kmdp-cta{display:flex;align-items:center;justify-content:center;gap:8px;clear:both;' +
      'background:var(--km-green-dark,#1a3c2e);color:#fff;text-decoration:none;' +
      'font-size:14px;font-weight:800;padding:11px 20px;border-radius:24px;' +
      'box-sizing:border-box;transition:background .15s}' +
    '.kmdp-cta:hover{background:var(--km-green-mid,#2d6a4f)}' +
    '.kmdp-fine{display:block;margin-top:8px;font-size:11px;color:#8a7a4e;text-align:center}' +
    // The sample card — deliberately the same shape the /bhav page builds.
    '.kmdp-card{background:#fff;border:1px solid #e3ece5;border-radius:12px;' +
      'overflow:hidden;box-shadow:0 3px 12px rgba(20,40,30,.12)}' +
    '.kmdp-photo{position:relative;height:72px;background:#f6f3e9;overflow:hidden;' +
      'display:flex;align-items:center;justify-content:center}' +
    // contain, exactly like the real card: centre-cropping a pack shot cuts
    // the label off, so the sample must not crop either.
    '.kmdp-photo img{max-height:100%;max-width:100%;object-fit:contain;display:block}' +
    '.kmdp-badge{position:absolute;top:5px;left:5px;background:var(--km-amber,#e9a825);' +
      'color:#fff;font-size:9px;font-weight:700;padding:1px 7px;border-radius:10px}' +
    '.kmdp-cbody{padding:7px 8px 9px;text-align:left}' +
    '.kmdp-cname{font-size:11.5px;font-weight:700;color:#1c2b22;line-height:1.3}' +
    '.kmdp-cen{display:block;font-size:9px;font-weight:600;color:#8a958f;margin-top:1px}' +
    '.kmdp-cprice{display:flex;align-items:baseline;gap:4px;flex-wrap:wrap;margin-top:5px}' +
    '.kmdp-cprice b{font-size:14px;font-weight:800;color:var(--km-green-mid,#2d6a4f)}' +
    '.kmdp-cmrp{font-size:10px;color:#8a958f;text-decoration:line-through}' +
    '.kmdp-coff{font-size:9.5px;font-weight:700;color:#c0392b}' +
    '.kmdp-cunit{font-size:10px;color:#8a958f;margin-top:2px}' +
    '.kmdp-cap{font-size:10px;color:#8a7a4e;margin:5px 0 0;line-height:1.35}' +
    '@media(min-width:721px){' +
      '.kmdp{margin:26px auto;padding:20px 22px;border-radius:16px}' +
      '.kmdp-in{display:flex;gap:22px;align-items:center}' +
      '.kmdp-body{flex:1;min-width:0}' +
      // order:2 keeps the card on the right on a wide screen, where the copy
      // reads first; the markup leads with it because the phone float needs it
      // to come before the text it wraps around.
      '.kmdp-demo{float:none;flex:none;width:172px;margin:0;order:2}' +
      '.kmdp-h{font-size:22px;margin-bottom:6px}' +
      '.kmdp-p{font-size:13.5px;line-height:1.62;margin-bottom:12px}' +
      '.kmdp-list{gap:6px;margin-bottom:15px}' +
      '.kmdp-list li{font-size:13px;line-height:1.5}' +
      '.kmdp-cta{display:inline-flex;font-size:14.5px;padding:11px 22px}' +
      '.kmdp-fine{text-align:left;font-size:11.5px}' +
      '.kmdp-photo{height:104px}' +
      '.kmdp-cname{font-size:12.5px}' +
      '.kmdp-cprice b{font-size:15.5px}' +
      '.kmdp-cap{font-size:11px;margin-top:8px}}';

  var HTML =
    '<span class="kmdp-eyebrow">🏪 दुकानदारों के लिए</span>' +
    '<div class="kmdp-in">' +
      '<div class="kmdp-demo">' +
        '<div class="kmdp-card">' +
          '<div class="kmdp-photo"><span class="kmdp-badge">बीज</span>' + PACK_IMG + '</div>' +
          '<div class="kmdp-cbody">' +
            '<div class="kmdp-cname">गेहूं बीज HD-2967</div>' +
            '<span class="kmdp-cen">Wheat Seeds HD-2967</span>' +
            '<div class="kmdp-cprice"><b>₹280</b>' +
              '<span class="kmdp-cmrp">₹350</span>' +
              '<span class="kmdp-coff">20% off</span></div>' +
            '<div class="kmdp-cunit">5 kg बैग</div>' +
          '</div>' +
        '</div>' +
        '<p class="kmdp-cap">↑ ऐसा दिखेगा आपका प्रोडक्ट</p>' +
      '</div>' +
      '<div class="kmdp-body">' +
        '<h2 class="kmdp-h">अपनी दुकान किसानों तक पहुंचाएं</h2>' +
        '<p class="kmdp-p">हर दिन हजारों किसान कृषि मित्र पर अपने जिले का भाव देखते हैं — ' +
        'और भाव देखने के बाद उनका अगला सवाल होता है “खाद-बीज कहां से लूं?”। ' +
        'आपके प्रोडक्ट ठीक उसी जगह, इसी तरह दिखेंगे।</p>' +
        '<ul class="kmdp-list">' +
          '<li><b>नाम, आपकी कीमत, MRP और छूट</b> — बिल्कुल दुकान जैसा कार्ड</li>' +
          '<li><b>कोई कमीशन नहीं</b> — किसान सीधे आपको फोन करता है</li>' +
          '<li><b>₹199 जिला + ₹50 प्रति फसल</b> — प्रति सीज़न (3 महीने) · ' +
            'जितने पेज, उतना पैसा</li>' +
        '</ul>' +
        '<a class="kmdp-cta" href="/dukanlisting">अपनी दुकान लिस्ट करें →</a>' +
        '<span class="kmdp-fine">व्यापारी · आढ़तिया · खाद-बीज डीलर · FPO · मिल</span>' +
      '</div>' +
    '</div>';

  // The markup is injected, so the stylesheet may as well be: one <style>,
  // once, only on pages that actually carry the block.
  function injectCSS() {
    if (document.getElementById('kmdp-css')) return;
    var st = document.createElement('style');
    st.id = 'kmdp-css';
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  function render() {
    var slots = document.querySelectorAll('[data-dukan-promo]');
    if (!slots.length) return;
    injectCSS();
    for (var i = 0; i < slots.length; i++) {
      // Idempotent: a page that also ships the markup statically, or a second
      // call, must not end up with the block twice.
      if (slots[i].getAttribute('data-dukan-promo-done')) continue;
      slots[i].className = (slots[i].className ? slots[i].className + ' ' : '') + 'kmdp';
      slots[i].innerHTML = HTML;
      slots[i].setAttribute('data-dukan-promo-done', '1');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
