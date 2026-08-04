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
# ONE DEALER OR NOTHING. `?d=<slug>` is required: a bare /pay, or a slug that
# resolves to nobody, renders a dead end rather than a generic fee and QR.
#
# It used to render that generic page, on the reasoning that a 404 in front of
# someone ready to pay is worse than an unnamed page. That trade was wrong —
# money arriving with no dealer attached cannot be matched to a listing, so
# nobody can be marked paid for it and the payer has to be chased for a
# screenshot just to establish who they were. The slug is also what becomes the
# UPI `tr` reference, which is the only thread tying a bank credit back to a
# row. A dealer always has his own link (admin.py::_pay_page_url), so the
# generic page was never on anyone's real path to paying.
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
    """(name, district, own_price) for the named dealer, or ("", "", None).

    Fails soft — Neon being asleep must not turn a payment page into an error
    page; it just loses the personalisation and falls back to the flat fee.

    `own_price` is what a /dukan/product account actually owes for its own
    district count (services/dealers.py::quote — ₹199 + ₹50 each after), so a
    dealer opening this page bare, with no ?amount= on the URL, is quoted his
    real subscription rather than the KM_LISTING_FEE default that has nothing
    to do with him. Plain values, not the ORM row: the session closes before
    the template renders and a detached instance is a trap for the next edit.
    """
    slug = (slug or "").strip()[:80]
    if not slug:
        return "", "", None
    db = None
    try:
        db = SessionLocal()
        row = db.query(Buyer).filter(Buyer.slug == slug).first()
        if not row:
            return "", "", None
        price = None
        if row.owner_user_id:
            from backend.services import dealers
            price = dealers.account_price(db, row.owner_user_id)
        return (row.name or "").strip(), (row.district or "").strip(), price
    except Exception:
        return "", "", None
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


@router.get("/pay", response_class=HTMLResponse)
def pay_page(d: str = "", amount: str = ""):
    canon = "https://krashimitra.in/pay"
    name, district, own_price = _dealer(d)

    def _dead_end(message: str) -> HTMLResponse:
        body = (f'<div class="pay-wrap"><div class="pay-card"><div class="pay-off">'
                f'{message}</div></div></div>')
        return _doc("पेमेंट — कृषि मित्र", "कृषि मित्र लिस्टिंग पेमेंट",
                    canon, "", body, active="", extra_css=_PAY_CSS,
                    robots="noindex, nofollow")

    if not upi.configured():
        # Never a fabricated VPA to keep the page pretty — a wrong destination
        # silently sends a dealer's money to a stranger.
        return _dead_end(
            '<b>पेमेंट अभी चालू नहीं है।</b><br>'
            'कृपया कृषि मित्र टीम से संपर्क करें — '
            '<a href="tel:+919870951001">+91 98709 51001</a>')

    # No dealer, no payable page. This used to render a generic fee + QR for a
    # bare /pay or a mistyped ?d=, on the reasoning that a 404 in front of
    # someone ready to pay is worse. It is not: money that arrives with no
    # dealer attached cannot be matched to a listing, so nobody can be marked
    # paid for it and the payer has to be chased for a screenshot to work out
    # who they even were. The dealer always reaches this page from his own
    # WhatsApp link (/pay?d=<slug>, admin.py::_pay_page_url), which carries the
    # slug into the UPI `tr` reference — that attribution is the whole point.
    if not name:
        return _dead_end(
            '<b>यह पेमेंट लिंक अधूरा है।</b><br>'
            'कृपया वही लिंक खोलें जो कृषि मित्र टीम ने आपको WhatsApp पर भेजा था, '
            'या हमें कॉल करें — <a href="tel:+919870951001">+91 98709 51001</a>')

    # An explicit ?amount= is how a renewal or a negotiated rate is sent, and it
    # wins — the admin panel puts the figure it just quoted in the WhatsApp
    # message onto the link itself, so the two can never disagree. Falling back
    # to this dealer's own subscription price before the flat KM_LISTING_FEE:
    # the default only makes sense for someone who has no account behind him.
    # clean_amount clamps whichever wins, so a hand-edited URL cannot produce a
    # ₹0 or a ₹9,00,000 QR.
    amt = upi.clean_amount(amount, default=own_price) if amount else (
        own_price or upi.DEFAULT_AMOUNT)
    pack = upi.collect(name, district, amount=amt, ref=(d or "").strip()[:80])

    # Always a named dealer past the guard above — the anonymous variant this
    # used to carry is gone with the generic page.
    heading = (f'<p class="pay-for">लिस्टिंग शुल्क</p>'
               f'<h2 class="pay-name">{escape(name)}</h2>'
               f'<p class="pay-place">{escape(district)}</p>')

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
