# ============================================================
# routes/pay.py
# /pay — the page a dealer opens to pay his listing fee.
#
# The rail is a upi:// deep link and a QR of the same link (services/upi.py).
# There is no gateway, no card form, and no field on this page that accepts
# anything sensitive: the dealer taps through to his own UPI app and the money
# moves bank-to-bank. Nothing here touches money, so nothing here can leak it.
#
# WHAT THIS PAGE MUST NEVER CLAIM. A upi:// hand-off reports nothing back, so
# this page cannot know whether payment happened and must never say it did.
# It renders a request to pay. Settlement is seen in the owner's bank app and
# typed into the admin panel by hand (dealers.record_payment) — a page that
# printed "पेमेंट हो गया" off a tapped link would be inventing a receipt.
#
# noindex, always. It is a private billing page for one named dealer, reached
# from a WhatsApp message, and it has no business in a sitemap or a SERP.
#
# UNKNOWN OR MISSING ?d= STILL RENDERS. The generic page (fee, QR, no dealer
# name) is the honest fallback for a mistyped link — the alternative is a 404
# in front of someone holding his phone open, ready to pay.
# ============================================================
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend.database.db import Buyer, SessionLocal
from backend.routes.bhav import _doc
from backend.services import upi

router = APIRouter()

_PAY_CSS = """
.pay-wrap{max-width:520px;margin:0 auto;padding:8px 0 40px}
.pay-card{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:26px 22px;text-align:center;
box-shadow:var(--shadow-sm)}
.pay-for{font-size:12.5px;color:var(--text-soft);margin:0 0 4px;letter-spacing:.02em}
.pay-name{font-size:20px;font-weight:700;color:var(--text-dark);margin:0 0 2px;line-height:1.4}
.pay-place{font-size:13px;color:var(--text-soft);margin:0 0 18px}
.pay-amt{font-size:40px;font-weight:800;color:var(--green-dark);margin:0;line-height:1.1}
.pay-amt-sub{font-size:12.5px;color:var(--text-soft);margin:2px 0 20px}
.pay-qr{display:inline-block;padding:14px;background:#fff;border:1px solid var(--border);
border-radius:var(--radius-sm);line-height:0;margin-bottom:6px}
.pay-qr svg{width:190px;height:190px;display:block}
.pay-scan{font-size:12px;color:var(--text-soft);margin:0 0 18px}
.pay-btn{display:block;width:100%;padding:15px 18px;background:var(--green-dark);color:#fff;
border:0;border-radius:var(--radius-sm);font-size:16px;font-weight:700;text-decoration:none;
cursor:pointer;box-shadow:var(--shadow-sm);font-family:inherit}
.pay-btn:hover{background:var(--green-mid)}
.pay-or{font-size:12px;color:var(--text-soft);margin:16px 0 8px}
.pay-vpa{display:flex;gap:8px;align-items:center;justify-content:center;flex-wrap:wrap;
padding:11px 14px;background:var(--green-pale);border-radius:var(--radius-sm);
font-family:var(--font-mono,monospace);font-size:14px;color:var(--text-dark);
word-break:break-all}
.pay-copy{padding:6px 12px;background:var(--white);border:1px solid var(--border);
border-radius:6px;font-size:12px;cursor:pointer;font-family:inherit;color:var(--text-mid);
flex-shrink:0}
.pay-copy:hover{border-color:var(--green-mid);color:var(--green-dark)}
.pay-after{margin-top:22px;padding:14px 16px;background:#fff8e6;border:1px solid #f0dfae;
border-radius:var(--radius-sm);font-size:13px;color:var(--text-mid);line-height:1.8;text-align:left}
.pay-after b{color:var(--text-dark)}
.pay-help{margin-top:18px;font-size:12.5px;color:var(--text-soft);line-height:1.8;text-align:center}
.pay-help a{color:var(--green-dark);font-weight:600}
.pay-off{padding:18px;background:#fff4f4;border:1px solid #f0c8c8;border-radius:var(--radius-sm);
font-size:14px;color:#8a2b2b;line-height:1.8;text-align:left}
@media(max-width:480px){.pay-card{padding:22px 16px}.pay-amt{font-size:34px}
.pay-qr svg{width:160px;height:160px}}
"""


def _dealer(slug: str):
    """The named dealer, or None. Fails soft — Neon being asleep must not turn a
    payment page into an error page; it just loses the personalisation."""
    slug = (slug or "").strip()[:80]
    if not slug:
        return None
    db = None
    try:
        db = SessionLocal()
        return db.query(Buyer).filter(Buyer.slug == slug).first()
    except Exception:
        return None
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


@router.get("/pay", response_class=HTMLResponse)
def pay_page(d: str = "", amount: str = ""):
    canon = "https://krashimitra.in/pay"
    row = _dealer(d)

    if not upi.configured():
        # Never a fabricated VPA to keep the page pretty — a wrong destination
        # silently sends a dealer's money to a stranger.
        body = ('<div class="pay-wrap"><div class="pay-card"><div class="pay-off">'
                '<b>पेमेंट अभी चालू नहीं है।</b><br>'
                'कृपया कृषि मित्र टीम से संपर्क करें — '
                '<a href="tel:+919870951001">+91 98709 51001</a>'
                '</div></div></div>')
        return _doc("पेमेंट — कृषि मित्र", "कृषि मित्र लिस्टिंग पेमेंट",
                    canon, "", body, active="", extra_css=_PAY_CSS,
                    robots="noindex, nofollow")

    name     = (row.name or "").strip() if row else ""
    district = (row.district or "").strip() if row else ""
    # An explicit ?amount= is how a renewal or a negotiated rate is sent; it is
    # clamped by clean_amount, so a hand-edited URL cannot produce a ₹0 or a
    # ₹9,00,000 QR.
    pack = upi.collect(name, district, amount=amount or None, ref=(d or "").strip()[:80])

    heading = (f'<p class="pay-for">लिस्टिंग शुल्क</p>'
               f'<h2 class="pay-name">{escape(name)}</h2>'
               f'<p class="pay-place">{escape(district)}</p>') if name else (
               '<p class="pay-for">कृषि मित्र</p>'
               '<h2 class="pay-name">लिस्टिंग शुल्क</h2>'
               '<p class="pay-place">खरीदार डायरेक्टरी</p>')

    qr = f'<div class="pay-qr">{pack["qr_svg"]}</div><p class="pay-scan">किसी भी UPI ऐप से QR स्कैन करें</p>' \
         if pack["qr_svg"] else ""

    body = f"""<div class="pay-wrap">
<div class="pay-card">
{heading}
<p class="pay-amt">₹{pack["amount"]}</p>
<p class="pay-amt-sub">प्रति माह · कोई अतिरिक्त चार्ज नहीं</p>
{qr}
<a class="pay-btn" href="{escape(pack["link"], quote=True)}">UPI ऐप में पे करें</a>
<p class="pay-or">या यह UPI ID कॉपी करके किसी भी ऐप में भेजें</p>
<div class="pay-vpa">
  <span id="pay-vpa-text">{escape(pack["vpa"])}</span>
  <button class="pay-copy" type="button" onclick="kmCopyVpa(this)">कॉपी</button>
</div>
<div class="pay-after">
  <b>पेमेंट के बाद:</b> स्क्रीनशॉट या UPI रेफरेंस नंबर WhatsApp पर भेज दीजिए —
  <a href="https://wa.me/919870951001">+91 98709 51001</a>।
  पुष्टि होते ही आपकी लिस्टिंग पर ✓ वेरिफाइड लग जाएगा।
</div>
<p class="pay-help">
  कोई दिक्कत हो तो कॉल करें — <a href="tel:+919870951001">+91 98709 51001</a><br>
  पैसा सीधे बैंक खाते में जाता है। कृषि मित्र आपका कार्ड या बैंक विवरण कभी नहीं माँगता।
</p>
</div>
</div>
<script>
function kmCopyVpa(btn){{
  var t = document.getElementById('pay-vpa-text');
  if(!t) return;
  var done = function(){{ var o = btn.textContent; btn.textContent = '✓ कॉपी हो गया';
    setTimeout(function(){{ btn.textContent = o; }}, 1800); }};
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(t.textContent).then(done).catch(function(){{}});
  }} else {{
    /* Older Android WebViews have no clipboard API — select the text so the
       dealer can long-press copy rather than retype a VPA by hand. */
    var r = document.createRange(); r.selectNodeContents(t);
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  }}
}}
</script>"""

    title = f"₹{pack['amount']} पेमेंट — {name}" if name else "लिस्टिंग पेमेंट — कृषि मित्र"
    return _doc(title[:68], "कृषि मित्र खरीदार डायरेक्टरी लिस्टिंग शुल्क का भुगतान।",
                canon, "", body, active="", extra_css=_PAY_CSS,
                robots="noindex, nofollow")
