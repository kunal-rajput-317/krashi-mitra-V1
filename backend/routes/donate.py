# ============================================================
# routes/donate.py
# /donate — the page for someone who wants to give money to कृषि मित्र.
#
# The other end of routes/pay.py. Same rail (a upi:// deep link plus a QR of
# that same link, services/upi.py), same hard limit: a UPI hand-off reports
# nothing back, so this page can render a request and never a receipt. Nothing
# here may print "धन्यवाद, पैसा मिल गया" off a tapped link.
#
# TWO DIFFERENCES FROM /pay, AND BOTH ARE DELIBERATE.
#
# 1. The amount is the giver's, not ours. /pay carries a fee we quoted, so the
#    figure is baked into the link and the dealer should not have to retype it.
#    A donation has no such number — naming one is a suggestion, not a bill —
#    so the QR is amount-free (upi.link(open_amount=True): the payer's own app
#    asks him) and the chips only pre-fill the button for whoever wants one tap.
#
# 2. It is public and indexable, where /pay is a private billing link for one
#    named dealer and is noindex. This page names nobody and is linked from the
#    site footer, so it is an ordinary page of the site.
#
# WHAT THE PAGE MUST KEEP SAYING. Three claims here are load-bearing and must
# survive any edit: कृषि मित्र is not a registered NGO/trust (so there is no 80G
# receipt to offer), a donation buys no listing, priority or better भाव, and a
# farmer should not be donating at all — the site is free for him and this page
# exists for the people who want it to keep running. Drop any of them and the
# page becomes the kind of solicitation a farmer has rightly been taught to
# distrust.
# ============================================================
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend.routes.bhav import SITE, _doc
from backend.services import upi

router = APIRouter()

# Suggestions, not tiers — there is nothing to buy, so none of these unlocks
# anything. Kept small on purpose: the audience is Indian and mostly on a
# phone, and a ₹5,000 chip on a page a farmer might open reads as a page not
# meant for him. `None` is the escape hatch: no am= at all, his app asks.
_AMOUNTS = [51, 101, 251, 501, None]
_DEFAULT = 101

_NOTE = "KrashiMitra donation"
_REF = "donate"

_CSS = """
.dn-wrap{max-width:560px;margin:0 auto;padding:4px 0 44px}
.dn-hero{text-align:center;padding:6px 4px 22px}
.dn-hero-icon{font-size:40px;line-height:1;margin-bottom:8px}
.dn-hero h1{font-family:var(--font-serif);font-size:26px;line-height:1.35;
color:var(--green-dark);margin:0 0 10px;font-weight:800}
.dn-hero p{font-size:15px;color:var(--text-mid);line-height:1.85;margin:0}
.dn-card{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:22px 18px;box-shadow:var(--shadow-sm);
text-align:center}
.dn-label{font-size:13px;color:var(--text-soft);margin:0 0 12px;letter-spacing:.02em}
.dn-chips{display:flex;flex-wrap:wrap;gap:9px;justify-content:center;margin:0 0 18px}
.dn-chip{flex:1 1 88px;min-width:88px;padding:13px 8px;background:var(--cream);
border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:inherit;
font-size:16px;font-weight:700;color:var(--text-mid);cursor:pointer;line-height:1.3}
.dn-chip:hover{border-color:var(--green-light)}
.dn-chip[aria-pressed="true"]{background:var(--green-pale);border-color:var(--green-mid);
color:var(--green-dark)}
.dn-chip-any{font-size:13.5px;font-weight:600}
.dn-btn{display:block;width:100%;padding:16px 18px;background:var(--green-dark);
color:#fff;border:0;border-radius:var(--radius-sm);font-size:17px;font-weight:700;
text-decoration:none;box-shadow:var(--shadow-sm);font-family:inherit}
.dn-btn:hover{background:var(--green-mid)}
.dn-or{font-size:12.5px;color:var(--text-soft);margin:18px 0 9px}
/* Every amount's QR is in the DOM; the picker only changes which is shown, so
   switching chips costs no request and cannot leave a stale code on screen. */
.dn-qrbox{display:none}
.dn-qrbox.on{display:block}
.dn-qr{display:inline-block;padding:13px;background:#fff;border:1px solid var(--border);
border-radius:var(--radius-sm);line-height:0}
.dn-qr svg{width:180px;height:180px;display:block}
.dn-vpa{display:flex;gap:8px;align-items:center;justify-content:center;flex-wrap:wrap;
padding:11px 14px;background:var(--green-pale);border-radius:var(--radius-sm);
font-family:var(--font-mono,monospace);font-size:14px;color:var(--text-dark);
word-break:break-all}
.dn-copy{padding:6px 12px;background:var(--white);border:1px solid var(--border);
border-radius:6px;font-size:12px;cursor:pointer;font-family:inherit;color:var(--text-mid);
flex-shrink:0}
.dn-copy:hover{border-color:var(--green-mid);color:var(--green-dark)}
.dn-safe{font-size:12px;color:var(--text-soft);line-height:1.75;margin:16px 0 0}
.dn-block{margin-top:26px;background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:20px 18px;box-shadow:var(--shadow-sm)}
.dn-block h2{font-family:var(--font-serif);font-size:19px;color:var(--green-dark);
margin:0 0 12px;font-weight:800;line-height:1.4}
.dn-list{list-style:none;margin:0;padding:0}
.dn-list li{position:relative;padding:0 0 0 26px;margin-bottom:11px;font-size:14.5px;
color:var(--text-mid);line-height:1.8}
.dn-list li:last-child{margin-bottom:0}
.dn-list li::before{content:"";position:absolute;left:6px;top:11px;width:7px;height:7px;
border-radius:50%;background:var(--green-light)}
.dn-list b{color:var(--text-dark)}
.dn-list a{color:var(--green-dark);font-weight:700}
.dn-honest{margin-top:26px;background:#fff8e6;border:1px solid #f0dfae;
border-radius:var(--radius-md);padding:20px 18px}
.dn-honest h2{font-family:var(--font-serif);font-size:19px;color:#7a5a12;
margin:0 0 12px;font-weight:800}
.dn-honest .dn-list li{color:#6b5622}
.dn-honest .dn-list li::before{background:#d9a640}
.dn-honest .dn-list b{color:#4a3a12}
.dn-honest .dn-list a{color:#7a5a12}
.dn-foot{margin-top:22px;text-align:center;font-size:13px;color:var(--text-soft);
line-height:1.9}
.dn-foot a{color:var(--green-dark);font-weight:700}
.dn-off{background:#fff4f4;border:1px solid #f0c8c8;border-radius:var(--radius-md);
padding:20px 18px;font-size:14.5px;color:#8a2b2b;line-height:1.9}
.dn-off a{color:#8a2b2b;font-weight:700}
@media(max-width:480px){.dn-hero h1{font-size:22px}.dn-card{padding:20px 14px}
.dn-block,.dn-honest{padding:18px 14px}.dn-qr svg{width:158px;height:158px}}
"""

_TITLE = "कृषि मित्र को सहयोग दें — दान करें"
_DESC = ("कृषि मित्र हर किसान के लिए मुफ़्त है। अगर इससे आपको मदद मिली है तो "
         "UPI से कोई भी राशि भेजकर इसे चलते रहने में सहयोग दीजिए।")
_CANON = f"{SITE}/donate"


def _page(body: str) -> HTMLResponse:
    # footer_note: the shell's default line promises a daily Agmarknet update,
    # which is true of a भाव page and meaningless here.
    return _doc(_TITLE, _DESC, _CANON, "", body, active="", extra_css=_CSS,
                footer_note="कृषि मित्र किसानों के लिए बना है और किसानों के लिए "
                            "मुफ़्त रहेगा।")


def _chip_label(amt) -> str:
    return "कोई भी राशि" if amt is None else f"₹{amt}"


def _btn_label(amt) -> str:
    return "UPI ऐप में दें" if amt is None else f"₹{amt} दें"


def _qr_caption(amt) -> str:
    """What the QR under a given chip actually does when it is scanned.

    Two different promises, and each has to be the true one: a QR built with
    `am=` pre-fills that figure in the scanner's app, while the open-amount one
    leaves the box empty for him to type. Printing the pre-fill line over an
    amount-free QR (or the reverse) sends someone looking for a number that is
    not going to appear."""
    if amt is None:
        return "या यह QR किसी भी UPI ऐप से स्कैन कीजिए — राशि आप वहीं भरिए"
    return f"या यह QR स्कैन कीजिए — ₹{amt} अपने आप भर जाएगा"


@router.get("/donate", response_class=HTMLResponse)
def donate_page():
    if not upi.configured():
        # No invented VPA to keep the page looking finished — a wrong
        # destination silently sends a well-wisher's money to a stranger.
        return _page(
            '<div class="dn-wrap"><div class="dn-off">'
            '<b>अभी ऑनलाइन दान चालू नहीं है।</b><br>'
            'अगर आप कृषि मित्र को सहयोग देना चाहते हैं तो हमें बता दीजिए — '
            '<a href="https://wa.me/919870951001">WhatsApp +91 98709 51001</a> '
            'या <a href="mailto:krashimitra038@gmail.com">krashimitra038@gmail.com</a>।'
            '</div></div>')

    # Chip, button link and QR are all built from ONE link per amount, in one
    # loop, so the three surfaces cannot disagree about what the giver picked.
    # The alternative — one link plus client-side string surgery on `&am=` —
    # puts a hand-edited amount one typo away from a real payment screen.
    #
    # Every QR ships inline and the picker only changes which one is shown. All
    # five together gzip to ~2 KB against ~0.6 KB for one, so the whole set
    # costs about 1.3 KB over the wire — cheaper than a QR library, and far
    # cheaper than a round trip to re-render one mid-payment. Nothing here needs
    # the network after the page has loaded.
    chips, qrs = [], []
    for amt in _AMOUNTS:
        href = upi.link(amt, note=_NOTE, ref=_REF, open_amount=(amt is None))
        selected = (amt == _DEFAULT)
        # "" is the open-amount key on both sides, so the chip and its QR match
        # by the same string a missing data-amt would produce.
        key = "" if amt is None else str(amt)
        cls = "dn-chip" + (" dn-chip-any" if amt is None else "")
        chips.append(
            f'<button type="button" class="{cls}" data-amt="{key}" '
            f'data-link="{escape(href, quote=True)}" '
            f'data-btn="{escape(_btn_label(amt), quote=True)}" '
            f'aria-pressed="{"true" if selected else "false"}">'
            f'{_chip_label(amt)}</button>')
        # Fails soft, exactly as it does on /pay: a QR that will not render must
        # not take the button and the copyable UPI ID down with it.
        svg = upi.qr_svg(href)
        if svg:
            qrs.append(
                f'<div class="dn-qrbox{" on" if selected else ""}" data-amt="{key}">'
                f'<p class="dn-or">{_qr_caption(amt)}</p>'
                f'<div class="dn-qr">{svg}</div></div>')

    default_link = upi.link(_DEFAULT, note=_NOTE, ref=_REF)
    qr = f'<div id="dn-qrs">{"".join(qrs)}</div>' if qrs else ""

    body = f"""<div class="dn-wrap">

<section class="dn-hero">
<div class="dn-hero-icon">🌾</div>
<h1>कृषि मित्र को सहयोग दीजिए</h1>
<p>मंडी भाव, मौसम, सरकारी योजना, कृषि सलाह — कृषि मित्र पर सब कुछ हर किसान के
लिए मुफ़्त है, और मुफ़्त ही रहेगा। पर इसे रोज़ चलाने में खर्च लगता है। अगर इस
साइट से आपको या आपके किसी जानने वाले को फ़ायदा हुआ है, तो जितना ठीक लगे उतना
भेज दीजिए।</p>
</section>

<section class="dn-card">
<p class="dn-label">कितना भेजना चाहेंगे?</p>
<div class="dn-chips" id="dn-chips">{"".join(chips)}</div>
<a class="dn-btn" id="dn-btn" href="{escape(default_link, quote=True)}">₹{_DEFAULT} दें</a>
{qr}
<p class="dn-or">या यह UPI ID कॉपी करके किसी भी ऐप से भेजिए</p>
<div class="dn-vpa">
  <span id="dn-vpa">{escape(upi.vpa())}</span>
  <button class="dn-copy" type="button" onclick="kmCopyVpa(this)">कॉपी</button>
</div>
<p class="dn-safe">पैसा सीधे बैंक खाते में जाता है। कृषि मित्र आपका कार्ड नंबर,
OTP, PIN या बैंक विवरण कभी नहीं माँगता — कोई माँगे तो वह कृषि मित्र नहीं है।</p>
</section>

<section class="dn-block">
<h2>पैसा कहाँ लगता है</h2>
<ul class="dn-list">
<li><b>सर्वर</b> — जिस पर हर दिन हज़ारों किसान भाव और मौसम देखते हैं।</li>
<li><b>डेटाबेस</b> — हर दिन का मंडी भाव सहेजा जाता है, तभी पिछले साल का रुझान
दिख पाता है।</li>
<li><b>नक्शे और तस्वीरें</b> — ज़िलेवार नक्शे और लेखों की तस्वीरें बनाना और
रखना।</li>
<li><b>हेल्पलाइन</b> — WhatsApp और फ़ोन, जिस पर किसान सीधे सवाल पूछते हैं।</li>
</ul>
</section>

<section class="dn-honest">
<h2>साफ़-साफ़ बात</h2>
<ul class="dn-list">
<li><b>किसान हैं तो दान मत कीजिए।</b> कृषि मित्र आपके लिए हमेशा मुफ़्त है। यह
पेज उन लोगों के लिए है जो इसे चलते हुए देखना चाहते हैं।</li>
<li><b>हम रजिस्टर्ड NGO या ट्रस्ट नहीं हैं।</b> इसलिए 80G की टैक्स छूट वाली
रसीद नहीं दे सकते। जो हम दे नहीं सकते, उसका वादा भी नहीं करते।</li>
<li><b>दान से कुछ ख़रीदा नहीं जाता।</b> कोई लिस्टिंग, कोई प्राथमिकता, कोई अलग
भाव नहीं मिलता। भाव सबके लिए एक ही रहते हैं।</li>
<li><b>UPI से भेजा पैसा वापस नहीं आता।</b> भेजने से पहले राशि एक बार देख
लीजिए।</li>
<li><b>पेमेंट के बाद यह पेज अपने आप कोई रसीद नहीं दिखाएगा</b> — UPI हमें उसी
वक़्त कुछ बताता नहीं। स्क्रीनशॉट
<a href="https://wa.me/919870951001">WhatsApp पर</a> भेज दीजिए, हम धन्यवाद
ज़रूर कहेंगे।</li>
</ul>
</section>

<section class="dn-block">
<h2>पैसे के बिना भी मदद हो सकती है</h2>
<ul class="dn-list">
<li>कृषि मित्र का लिंक अपने गाँव या मंडी के WhatsApp ग्रुप में भेज दीजिए।</li>
<li>अपने राज्य का <a href="{SITE}/bhav">रोज़ का भाव चैनल</a> जॉइन कीजिए और
साथियों को भी जोड़िए।</li>
<li>कोई भाव गलत या पुराना दिखे तो
<a href="https://wa.me/919870951001">बता दीजिए</a> — यही सबसे बड़ी मदद है।</li>
<li>आपकी मंडी या फसल यहाँ नहीं है? नाम भेज दीजिए, हम जोड़ेंगे।</li>
</ul>
</section>

<p class="dn-foot">
कोई सवाल हो तो <a href="tel:+919870951001">+91 98709 51001</a> पर कॉल कीजिए<br>
या लिखिए — <a href="mailto:krashimitra038@gmail.com">krashimitra038@gmail.com</a>
</p>

</div>

<script>
(function(){{
  var chips = document.getElementById('dn-chips');
  var btn = document.getElementById('dn-btn');
  if (!chips || !btn) return;
  chips.addEventListener('click', function(e){{
    var c = e.target.closest('.dn-chip');
    if (!c) return;
    var all = chips.querySelectorAll('.dn-chip');
    for (var i = 0; i < all.length; i++) all[i].setAttribute('aria-pressed', 'false');
    c.setAttribute('aria-pressed', 'true');
    /* href, label and QR all move together — a button reading "₹501 दें", or a
       QR that still encodes ₹101, is the one bug this page cannot afford. */
    btn.href = c.getAttribute('data-link');
    btn.textContent = c.getAttribute('data-btn');
    var amt = c.getAttribute('data-amt') || '';
    var boxes = document.querySelectorAll('.dn-qrbox');
    for (var j = 0; j < boxes.length; j++) {{
      /* add/remove rather than classList.toggle(name, force): the two-argument
         form is missing from the older Android WebViews this site still gets. */
      if ((boxes[j].getAttribute('data-amt') || '') === amt) boxes[j].classList.add('on');
      else boxes[j].classList.remove('on');
    }}
  }});
}})();
function kmCopyVpa(btn){{
  var t = document.getElementById('dn-vpa');
  if (!t) return;
  var done = function(){{ var o = btn.textContent; btn.textContent = '✓ कॉपी हो गया';
    setTimeout(function(){{ btn.textContent = o; }}, 1800); }};
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(t.textContent).then(done).catch(function(){{}});
  }} else {{
    /* Older Android WebViews have no clipboard API — select the text so it can
       be long-pressed rather than retyped by hand. */
    var r = document.createRange(); r.selectNodeContents(t);
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  }}
}}
</script>"""

    return _page(body)
