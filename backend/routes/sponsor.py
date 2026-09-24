# ============================================================
# routes/sponsor.py
# /sponsor — the page a brand reads before deciding to pay us.
#
# WHY IT EXISTS. Every money surface on this site was built and then left
# unreachable: /dukanlisting is only linked from inside /bhav, /donate from two
# server-rendered footers, and the placement tiers in services/placements.py
# have no public page at all. A company that wanted to sponsor krashimitra.in
# could not find out how, or what it cost, without phoning. This page is the
# ask, standing where anyone can read it, working while nobody is awake — which
# is the only kind of selling this project has ever actually done.
#
# IT IS IN ENGLISH, AND THAT IS THE ONE DELIBERATE EXCEPTION ON THIS SITE.
# Every other page is written in the language of the farmer who reads it. This
# one is read by a marketing manager in Delhi, Hyderabad or Ahmedabad, and the
# media kit they will forward internally has to be forwardable. lang="en" is
# passed to _doc for exactly that reason — see the note there about a title
# whose language disagrees with the tag.
#
# THE NUMBERS ARE NOT IN THIS FILE. They come from services/mediakit.py, which
# refreshes from Search Console daily and withholds everything once the
# snapshot ages out. A hand-typed audience figure is true the week it is typed
# and a lie by the next quarter, and the single thing a first-time sponsor is
# buying from an unknown site is our word. So the page has two states: real
# dated numbers, or an honest line saying the figures are available on request.
# There is no third state where it prints a guess.
#
# WHAT IT MUST NEVER DO — the [[feedback_never-a-legal-exposure]] list applied
# to selling rather than to advice:
#   • No CPM, reach or ROI claim we would have to defend. Print the measured
#     numbers and the price; let the buyer do his own division.
#   • No "trusted by" / "as seen in" / partner logos we do not have.
#   • No promise of leads, enquiries or sales. We sell a labelled placement on
#     a page. What it converts to is not ours to promise.
#   • No invoice or GST claim while there is no registered entity — see the
#     billing section, which says so in plain words rather than going quiet.
# ============================================================
from html import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from backend.routes.bhav import SITE, _crumb_ld, _doc, _faq, _ld
from backend.services import mediakit, sponsors

router = APIRouter()

# Written for the words a brand's marketing team actually searches —
# "advertise to farmers", "agri advertising India", "rural marketing" — not for
# our own name, which no prospect knows yet. Inside [[serp-length-budgets]].
_TITLE = "Advertise to Indian Farmers — Agri Brand Sponsorship Rates"
_DESC = ("Reach Hindi-speaking farmers on mandi price, crop advice and scheme "
         "pages. Category exclusivity, fixed 60-day rates, talk to us directly.")
_CANON = f"{SITE}/sponsor"

EMAIL = "krashimitra038@gmail.com"
PHONE = "+91 98709 51001"
PHONE_E164 = "+919870951001"

_CSS = """
.sp-wrap{max-width:820px;margin:0 auto;padding:4px 0 52px}
.sp-hero{padding:8px 4px 26px}
.sp-kicker{font-size:12.5px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;
color:#2d6a4f;margin:0 0 8px}
.sp-faq .faq{border-top:1px solid #e5e9e6;padding:12px 0}
.sp-faq .faq h3{font-size:15.5px;margin:0 0 6px}
.sp-faq .faq p{margin:0;font-size:14.5px;line-height:1.6}
.sp-hero h1{font-family:var(--font-serif);font-size:30px;line-height:1.3;
color:var(--green-dark);margin:0 0 14px;font-weight:800}
.sp-hero p{font-size:16px;color:var(--text-mid);line-height:1.8;margin:0 0 10px}
.sp-block{margin:34px 0 0}
.sp-block h2{font-family:var(--font-serif);font-size:22px;color:var(--green-dark);
margin:0 0 14px;font-weight:800}
.sp-block p{font-size:15px;color:var(--text-mid);line-height:1.85;margin:0 0 12px}
.sp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.sp-stat{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-sm);padding:16px 14px}
.sp-stat b{display:block;font-size:26px;font-weight:800;color:var(--green-dark);
line-height:1.2;font-variant-numeric:tabular-nums}
.sp-stat span{display:block;font-size:12.5px;color:var(--text-soft);margin-top:5px;
line-height:1.5}
.sp-asof{font-size:12.5px;color:var(--text-soft);margin:10px 0 0;line-height:1.6}
.sp-aud{margin:0 0 18px}
.sp-aud p{font-size:15px;color:var(--text-mid);line-height:1.85;margin:0 0 12px}
.sp-aud b{color:var(--text-dark)}
.sp-nonum{background:var(--cream);border:1px dashed var(--border);
border-radius:var(--radius-sm);padding:18px 16px;font-size:14.5px;
color:var(--text-mid);line-height:1.8;margin:0}
.sp-table{width:100%;border-collapse:collapse;font-size:14px;margin:0 0 8px}
.sp-table th,.sp-table td{text-align:left;padding:10px 9px;
border-bottom:1px solid var(--border);vertical-align:top}
.sp-table th{font-size:12px;letter-spacing:.05em;text-transform:uppercase;
color:var(--text-soft);font-weight:700}
.sp-table td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.sp-tiers{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.sp-tier{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:20px 18px;display:flex;flex-direction:column;position:relative}
.sp-tier.on,.sp-tier.highlight{border-color:var(--green-mid);border-width:2px;padding:19px 17px;box-shadow:0 4px 16px rgba(44,92,46,0.08)}
.sp-badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;background:var(--green-pale);color:var(--green-dark);padding:3px 9px;border-radius:12px;margin:0 0 10px;width:fit-content}
.sp-tier h3{font-size:16px;font-weight:800;color:var(--green-dark);margin:0 0 4px}
.sp-price{font-size:27px;font-weight:800;color:var(--text-dark);line-height:1.2;
margin:0 0 3px;font-variant-numeric:tabular-nums}
.sp-price-extra{font-size:13.5px;color:var(--text-soft);font-weight:500;display:inline-block;margin-left:4px}
.sp-per{font-size:12.5px;color:var(--text-soft);margin:0 0 14px}
.sp-tier ul{margin:0;padding:0 0 0 17px}
.sp-tier li{font-size:13.5px;color:var(--text-mid);line-height:1.7;margin:0 0 9px}
.sp-list{margin:0;padding:0 0 0 18px}
.sp-list li{font-size:15px;color:var(--text-mid);line-height:1.8;margin:0 0 11px}
.sp-list b{color:var(--text-dark)}
.sp-honest{background:var(--green-pale);border:1px solid var(--green-light);
border-radius:var(--radius-md);padding:22px 20px}
.sp-honest h2{margin-top:0}
.sp-cta{background:var(--white);border:1px solid var(--border);
border-radius:var(--radius-md);padding:24px 20px;text-align:center;margin:34px 0 0}
.sp-cta h2{margin-bottom:8px}
.sp-btn{display:inline-block;padding:15px 30px;background:var(--green-dark);
color:#fff;border-radius:var(--radius-sm);font-size:16px;font-weight:700;
text-decoration:none;margin:8px 6px 0}
.sp-btn.alt{background:var(--white);color:var(--green-dark);
border:1.5px solid var(--green-mid)}
@media(max-width:480px){.sp-hero h1{font-size:25px}.sp-price{font-size:24px}}
"""


def _n(v) -> str:
    """Indian digit grouping — 4,75,120, not 475,120. A media kit read in
    Delhi that formats its own audience the American way reads as a template
    somebody else filled in."""
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        return "—"
    s, neg = str(abs(v)), v < 0
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + s


def _numbers_block() -> str:
    """What the PUBLIC page says about the audience: who, never how many.

    THE FIGURES ARE DELIBERATELY ABSENT. Impressions, the per-section
    breakdown and the URL count are a competitive disclosure — they tell every
    other agri publisher which surfaces work and how large they are, which is
    worth more to them than to the one brand we are pitching. A media kit is
    something you hand to a prospect, not something you post.

    So this describes the audience in words a brand can act on, and the
    measured version lives behind a per-prospect link (`/sponsor/kit/...`)
    that we send deliberately. `mediakit.stats()` is not called here at all —
    not conditionally, not in a comment. The numbers cannot leak from a branch
    that does not exist.
    """
    return (
        '<div class="sp-aud">'
        '<p><b>Who is on the other side of the screen.</b> A farmer in the '
        'Hindi belt — Uttar Pradesh, Madhya Pradesh, Rajasthan, Bihar — and '
        'increasingly Maharashtra, Karnataka and Tamil Nadu in their own '
        'languages. He is on a phone, on mobile data, and he arrived from a '
        'Google search rather than from social media.</p>'
        '<p><b>What he came to do.</b> Check this morning’s rate for his crop '
        'in his own mandi. Work out a fertilizer dose per acre. Find out '
        'whether a scheme applies to him. Look up his village on a map. These '
        'are decisions with money attached, taken in the days before he '
        'spends.</p>'
        '<p><b>Which surfaces carry it.</b> Mandi prices across every '
        'state and district; village and district maps; Hindi guides on dosage, '
        'disease and season; livestock and the egg rate; government '
        'schemes; and a farmer-to-farmer marketplace.</p>'
        '</div>'
        '<p class="sp-nonum"><b>The traffic figures are not published on this '
        'page, on purpose.</b> They are a competitive disclosure, and posting '
        'them would tell every other agri site exactly what works here. Ask us '
        'and we will send you a private link to the full media kit: search '
        'impressions, visits, the per-section breakdown, device and country '
        'split, and the window they were measured over — pulled straight from '
        'Google Search Console, never typed in by hand. We will also walk you '
        'through the Search Console property on a call, so the numbers come '
        'from Google rather than from us.</p>')


def _measured_block(st: dict) -> str:
    """The real figures. ONLY ever called from the token-gated kit route.

    Keep it that way: the moment this is reachable from /sponsor, the whole
    privacy split is undone and the numbers are public again. The public page
    calls _numbers_block(), which never touches mediakit.stats().
    """
    t = st["totals"]
    mob = next((d["pct"] for d in st.get("devices", [])
                if str(d.get("k", "")).upper() == "MOBILE"), None)
    ind = next((c["pct"] for c in st.get("countries", [])
                if str(c.get("k", "")).lower() in ("ind", "in", "india")), None)

    cards = [
        (_n(t["impressions"]), f'search impressions in {st["window_days"]} days'),
        (_n(t["per_day"]), "impressions per day"),
        (_n(t["clicks"]), "visits from search"),
        (_n(t["urls"]), "pages that earned an impression"),
    ]
    if mob is not None:
        cards.append((f"{mob:g}%", "on a phone"))
    if ind is not None:
        cards.append((f"{ind:g}%", "in India"))

    stats = "".join(f'<div class="sp-stat"><b>{escape(v)}</b>'
                    f'<span>{escape(lab)}</span></div>' for v, lab in cards)

    rows = ""
    labels = dict(mediakit.SECTIONS)
    for prefix, acc in sorted((st.get("sections") or {}).items(),
                              key=lambda kv: -kv[1]["i"]):
        if acc["i"] <= 0:
            continue
        rows += (f'<tr><td><b>{escape(prefix)}</b><br>'
                 f'<span style="font-size:12.5px;color:var(--text-soft)">'
                 f'{escape(labels.get(prefix, ""))}</span></td>'
                 f'<td class="n">{_n(acc["i"])}</td>'
                 f'<td class="n">{_n(acc["urls"])}</td></tr>')
    table = (f'<table class="sp-table"><thead><tr><th>Section</th>'
             f'<th class="n">Impressions</th><th class="n">Pages</th></tr>'
             f'</thead><tbody>{rows}</tbody></table>') if rows else ""

    return (f'<div class="sp-grid">{stats}</div>'
            f'<p class="sp-asof">Google Search Console, {escape(st["start"])} to '
            f'{escape(st["end"])}, pulled automatically on '
            f'{escape(st["fetched_on"])} — nothing here is hand-typed. We will '
            f'walk you through the property itself on a call.</p>'
            f'<h2>Where the traffic is</h2>{table}'
            f'<p class="sp-asof">Same window. Sections not listed (homepage, '
            f'/about, login) carry real traffic but are not sold.</p>')


def sponsors_sections():
    return mediakit.SECTIONS


def _tiers_block() -> str:
    out = []
    for i, tier in enumerate(sponsors.RATE_CARD):
        gets = "".join(f"<li>{escape(g)}</li>" for g in tier["gets"])
        on = " highlight" if tier.get("highlight") else ""
        badge = f'<span class="sp-badge">{escape(tier["badge"])}</span>' if tier.get("badge") else ""
        unit = tier.get("unit", f"60-day campaign · {sponsors.MIN_DAYS}-day minimum")
        price_num = str(tier["price"])
        price_extra = escape(tier.get("price_extra", ""))
        out.append(
            f'<div class="sp-tier{on}">'
            f'{badge}'
            f'<h3>{escape(tier["name"])}</h3>'
            f'<p class="sp-price" data-price="{price_num}">₹{_n(tier["price"])}'
            f'{f"<span class=\"sp-price-extra\">{price_extra}</span>" if price_extra else ""}</p>'
            f'<p class="sp-per">{escape(unit)}</p>'
            f'<ul>{gets}</ul></div>')
    return f'<div class="sp-tiers">{"".join(out)}</div>'


def _price_range(tier: dict) -> str:
    extra = (tier.get("price_extra") or "").strip()
    if extra.startswith("–"):
        return f"₹{_n(tier['price'])} to {extra.lstrip('– ').strip()}"
    return f"₹{_n(tier['price'])}{extra}"


def _faqs() -> list[tuple[str, str]]:
    """Visible on the page AND emitted as FAQPage — one list, via bhav._faq.
    Prices are read from RATE_CARD so an edit there cannot leave a stale
    figure in the answer. Nothing here promises a result: no reach, no leads,
    no sales — see the WHAT IT MUST NEVER DO list at the top."""
    tiers = "; ".join(f"{t['name']}: {_price_range(t)}" for t in sponsors.RATE_CARD)
    return [
        ("How much does it cost to advertise to farmers on KrashiMitra?",
         f"Fixed rates for a 60-day campaign, not an auction. {tiers}. "
         "The final price depends on category, states and scope, and is agreed "
         "with you directly before anything goes live."),
        ("Who sees a sponsored placement?",
         "Farmers in the Hindi belt — Uttar Pradesh, Madhya Pradesh, Rajasthan, "
         "Bihar — and increasingly Maharashtra, Karnataka and Tamil Nadu, almost "
         "all on a phone, arriving from a Google search to check a mandi price, "
         "a fertilizer dose, a crop problem or a government scheme."),
        ("Can a competitor advertise next to us?",
         "No. Sponsorships are sold with category exclusivity: while your "
         "campaign runs, no other brand in your category is placed on the site."),
        ("Can we see the traffic numbers before we pay?",
         "Yes. Every brand we talk to gets a private media kit link with the "
         "verified Google Search Console figures, and we will walk you through "
         "the Search Console property on a call."),
        ("Is the mandi price or advice ever changed for a sponsor?",
         "No. Prices, advice and rankings are not for sale at any price. A "
         "sponsor gets a clearly labelled placement beside them, never "
         "influence over them."),
        ("How do we start?",
         f"Message us on WhatsApp at {PHONE} or email {EMAIL} with the category "
         "you sell into and the states that matter to you."),
    ]


def _org_ld() -> dict:
    return {"@context": "https://schema.org", "@type": "Organization",
            "name": "KrashiMitra", "url": SITE,
            "logo": f"{SITE}/assets/logo-512.png",
            "contactPoint": [{"@type": "ContactPoint",
                              "contactType": "sales",
                              "telephone": PHONE_E164,
                              "email": EMAIL,
                              "areaServed": "IN",
                              "availableLanguage": ["en", "hi"]}]}


@router.get("/sponsor", response_class=HTMLResponse)
def sponsor_page():
    never = "".join(f"<li>{escape(x)}</li>" for x in sponsors.NEVER_FOR_SALE)
    faq_html, faq_ld = _faq(_faqs())
    ld = _ld(_org_ld(), faq_ld,
             _crumb_ld([("KrashiMitra", f"{SITE}/"), ("Sponsor", _CANON)]))

    body = f"""<div class="sp-wrap">

<section class="sp-hero">
<p class="sp-kicker">Advertising &amp; sponsorship · agri brands</p>
<h1>Reach a farmer at the moment he is deciding to spend</h1>
<p>KrashiMitra is a free Hindi farming site. A farmer opens it to check what
his crop sold for in his own mandi this morning, what to spray, how much urea
an acre needs, or whether he qualifies for a scheme. He arrives from Google,
on a phone, with a question he is about to act on.</p>
<p>That is a narrow audience and we will not pretend otherwise. It is also the
exact person a seed, fertilizer, crop-protection, irrigation or farm-finance
brand spends its year trying to reach, and reaches mostly through dealers who
never report back.</p>
</section>

<section class="sp-block">
<h2>The audience</h2>
{_numbers_block()}
</section>

<section class="sp-block">
<h2>What you can sponsor</h2>
<p>Fixed campaign rates for the 60-day Kharif Harvest & Rabi Sowing window,
not an ad auction and not a CPM. The verified Search Console figures go to
every brand we talk to, privately, and the pricing is published here — a
flattering rate calculated on our side is the first thing a media buyer checks
and the fastest way for us to lose one.</p>
{_tiers_block()}
<p class="sp-asof">Every placement carries a visible <b>प्रायोजक · Sponsored</b>
label and a <code>rel="nofollow sponsored"</code> link. Creative is a logo and
one line in your own words; we host the image ourselves rather than hotlinking
it, so it cannot break on a farmer's 2G connection.</p>
</section>

<section class="sp-block sp-honest">
<h2>What is not for sale, at any price</h2>
<ul class="sp-list">{never}</ul>
<p>This list is the product. A farmer trusts a price here because nobody can
pay to move it, and a sponsor is buying a place beside that trust rather than
a licence to spend it.</p>
</section>

<section class="sp-block">
<h2>Billing, plainly</h2>
<ul class="sp-list">
<li><b>KrashiMitra is not yet a registered company</b>, so we cannot issue a
GST tax invoice today. Registration is the one thing standing between us and a
normal vendor relationship, and we would rather say that here than discover it
with your accounts team after you have said yes.</li>
<li><b>Payment is by UPI or bank transfer</b>, and we issue a signed receipt
with the dates and the placement on it. If your process needs a GST invoice,
tell us at the first call — it changes our timeline, not the price.</li>
<li><b>60-day campaign terms, structured 50/50.</b> 50% advance on contract
signing and placement activation; 50% at the 30-day milestone. A sponsor card
needs a full crop cycle before anyone can honestly measure impact.</li>
<li><b>Verified telemetry reports.</b> You get bi-weekly performance summaries —
pages your card appeared on, impressions, and verified taps on your link,
measured directly from our own server telemetry.</li>
<li><b>Clean, straightforward terms.</b> No auto-renewal you have to remember
to cancel, and first right of refusal on your category for the upcoming season.</li>
</ul>
</section>

<section class="sp-block">
<h2>Why sponsor this rather than run ads</h2>
<ul class="sp-list">
<li><b>Category exclusivity.</b> An ad network sells your competitor the slot
beside yours. We will not, and at this size we can actually promise it.</li>
<li><b>The pages keep earning.</b> A guide we write for your category stays
ranked and keeps being read after the quarter it was paid for. A banner
campaign stops the day the budget does.</li>
<li><b>It is Hindi, and it is ours.</b> We write, host and rank the content —
no agency markup, no translation round, no media plan.</li>
<li><b>You can check everything.</b> Verified Search Console export summary,
our server logs for taps, and the site itself, which is public.</li>
</ul>
</section>

<section class="sp-block sp-faq">
<h2>Questions brands ask first</h2>
{faq_html}
</section>

<section class="sp-cta">
<h2>Talk to us</h2>
<p>Tell us the category you sell into and the states that matter, and we will
send the verified Search Console export summary for exactly those pages before you
commit to anything.</p>
<a class="sp-btn" href="https://wa.me/{PHONE_E164}">WhatsApp {escape(PHONE)}</a>
<a class="sp-btn alt" href="mailto:{EMAIL}?subject=Sponsorship%20enquiry%20%E2%80%94%20KrashiMitra">{escape(EMAIL)}</a>
</section>

<section class="sp-block">
<h2>Smaller than this?</h2>
<p>If you are a local input dealer, seed shop or trader rather than a brand,
the site sells single-district and single-crop listings from ₹199 —
<a href="{SITE}/dukanlisting">list your shop here</a>. And if you are not
buying anything but want the site to keep running, there is a
<a href="{SITE}/donate">support page</a>.</p>
</section>

</div>"""

    return _doc(_TITLE, _DESC, _CANON, "", body, ld=ld, active="",
                extra_css=_CSS, lang="en",
                footer_note="KrashiMitra is free for farmers and always will be.")


@router.get("/sponsor/kit/{token}", response_class=HTMLResponse)
def sponsor_kit(token: str):
    """The measured media kit, for one named prospect.

    UNLINKED, UNGUESSABLE, UNINDEXED — the three together are what keep the
    figures private. Nothing on the site links here, the token is a truncated
    HMAC so the URL cannot be enumerated, and the response carries
    X-Robots-Tag as well as a meta robots tag because a crawler that reaches a
    URL through a forwarded email obeys the header long before it parses the
    body.

    A bad token gets the same 404 a missing page gets. Not 401, not "invalid
    link" — an error that distinguishes "wrong signature" from "no such route"
    confirms to whoever is probing that there is something here worth probing.

    With KM_SPONSOR_KIT_SECRET unset, sponsors.kit_verify() refuses every
    token and this route is closed to everyone. That is the intended default.
    """
    who = sponsors.kit_verify(token)
    if not who:
        raise HTTPException(status_code=404)

    st = mediakit.stats()
    if not st:
        body = ('<div class="sp-wrap"><section class="sp-hero">'
                '<h1>Media kit</h1><p class="sp-nonum">The automated Search '
                'Console pull has not run recently enough for us to stand '
                'behind these figures, so they are withheld rather than shown '
                'stale. Please ask and we will refresh and resend — or we will '
                'walk you through the Search Console property directly.</p>'
                '</section></div>')
    else:
        body = (f'<div class="sp-wrap"><section class="sp-hero">'
                f'<h1>Media kit</h1>'
                f'<p>Prepared for <b>{escape(who)}</b>. Please treat these '
                f'figures as confidential — they are not published anywhere on '
                f'the site, and this link was generated for you alone.</p>'
                f'</section><section class="sp-block">{_measured_block(st)}'
                f'</section>'
                f'<section class="sp-block"><h2>What you can sponsor</h2>'
                f'{_tiers_block()}</section></div>')

    res = _doc("Media kit — KrashiMitra", "Private media kit.",
               f"{SITE}/sponsor", "", body, active="", extra_css=_CSS,
               lang="en", robots="noindex, nofollow, noarchive",
               journey=False,
               footer_note="Private media kit — please do not circulate.")
    res.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    # An intermediary caching one prospect's kit and serving it to the next
    # visitor would undo every other precaution here.
    res.headers["Cache-Control"] = "private, no-store, max-age=0"
    return res
