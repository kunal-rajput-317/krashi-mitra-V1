# ============================================================
# routes/sawal.py
# कृषि मित्र — किसान के असली सवाल (/sawal)
#
# Server-rendered Hindi Q&A pages built from the Government of India's
# Kisan Call Centre transcripts — real questions farmers phoned in, with
# the answer the government's agriculture expert gave them.
#
# Same pattern as bhav.py / product.py: the page shell (CSS tokens,
# sticky header, footer, FAQ + breadcrumb JSON-LD) is imported straight
# from bhav.py rather than duplicated, so every SEO surface stays
# visually identical for free.
#
# The content is NOT the raw feed — see backend/services/kcc_service.py
# for the safety gate. Roughly 2% of raw answers give advice for a
# different crop than the row is filed under, and these answers name
# pesticides and doses, so only crop-verified Hindi answers are stored
# and only stored rows are ever rendered here.
#
# Serves /sawal (hub), /sawal/{crop} and /sawal/sitemap.xml.
# ============================================================

from html import escape
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from backend.routes.bhav import _doc, _faq, _crumb_ld, _ld, _not_found
from backend.services.kcc_service import (
    CROPS, get_qa, crops_with_qa, MIN_QA_TO_PUBLISH,
)

router = APIRouter()

SITE = "https://krashimitra.in"

_SAWAL_CSS = """
.sawal-intro{font-size:14px;color:var(--text-mid);line-height:1.75;max-width:720px;
margin:0 0 22px;padding:14px 18px;background:var(--white);border:1px solid var(--border);
border-left:4px solid var(--sky);border-radius:var(--radius-sm)}
.sawal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.sawal-tile{display:flex;flex-direction:column;gap:3px;padding:14px 16px;background:var(--white);
border:1px solid var(--border);border-radius:var(--radius-sm);text-decoration:none;
transition:border-color .15s,transform .15s}
.sawal-tile:hover{border-color:var(--green-mid);transform:translateY(-2px)}
.sawal-tile b{font-size:16px;color:var(--text-dark)}
.sawal-tile span{font-size:11.5px;color:var(--text-soft)}
.topic-h{margin:26px 0 10px;font-size:17px;color:var(--text-dark)}
.qa{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-sm);
padding:14px 18px;margin-bottom:12px}
.qa-q{font-size:14.5px;font-weight:700;color:var(--text-dark);margin:0 0 8px;line-height:1.6}
.qa-a{font-size:14px;color:var(--text-mid);line-height:1.8;margin:0}
.qa-src{display:block;margin-top:10px;font-size:11px;color:var(--text-soft)}
.sawal-note{font-size:12px;color:var(--text-soft);line-height:1.7;margin-top:22px;
padding:12px 16px;background:#fff8e6;border:1px solid #f0dfae;border-radius:var(--radius-sm)}
"""


def _qa_card(qa: dict, topic_hi: str, crop_hi: str) -> tuple[str, str, str]:
    """Returns (html, q_text, a_text) so the FAQ schema is generated from the
    very same strings that are visible — never hand-written alongside them.

    The question is the Hindi one kcc_service.derive_question() recovered from
    the answer's own purpose clause; the transcripts' English/Hinglish
    QueryText is never shown.
    """
    q = qa.get("question") or f"{crop_hi} में {topic_hi}"
    a = qa["answer"]
    where = " · ".join(x for x in [qa.get("district"), qa.get("state")] if x)
    when = f"{qa['year']}" if qa.get("year") else ""
    src = " · ".join(x for x in [where, when] if x)
    src_html = (f'<span class="qa-src">स्रोत: किसान कॉल सेंटर (भारत सरकार)'
                f'{" — " + escape(src) if src else ""}</span>')
    html = (f'<div class="qa"><p class="qa-q">{escape(q)}</p>'
            f'<p class="qa-a">{escape(a)}</p>{src_html}</div>')
    return html, q, a


@router.get("/sawal", response_class=HTMLResponse)
@router.get("/sawal/", response_class=HTMLResponse)
def sawal_hub():
    crops = crops_with_qa()
    if not crops:
        return _not_found()

    tiles = "".join(
        f'<a class="sawal-tile" href="{SITE}/sawal/{slug}">'
        f'<b>{escape(hi)}</b><span>{n} सवाल-जवाब</span></a>'
        for slug, hi, n in crops)
    total = sum(n for _s, _h, n in crops)

    body = f"""<h1>किसान के असली सवाल — और सरकारी जवाब</h1>
<p class="sawal-intro">ये सवाल किसी ने बनाए नहीं हैं। ये असली सवाल हैं जो किसानों ने
<strong>किसान कॉल सेंटर (भारत सरकार)</strong> पर फोन करके पूछे, और नीचे वही जवाब हैं जो
कृषि विशेषज्ञों ने उन्हें दिए। फसल चुनें और अपने काम का सवाल देखें।</p>
<div class="sawal-grid">{tiles}</div>
<p class="sawal-note">⚠️ ये जवाब सरकारी रिकॉर्ड से लिए गए हैं और सामान्य जानकारी के लिए हैं।
कोई भी दवा या खाद डालने से पहले अपने नज़दीकी कृषि अधिकारी या KVK से ज़रूर पूछें —
मात्रा फसल की अवस्था और मौसम पर निर्भर करती है।</p>"""

    return _doc(
        title=f"किसान के असली सवाल और जवाब — {len(crops)} फसलें | कृषि मित्र",
        desc=("किसान कॉल सेंटर (भारत सरकार) पर किसानों द्वारा पूछे गए असली सवाल और "
              f"कृषि विशेषज्ञों के जवाब — {total}+ सवाल-जवाब, फसलवार, हिंदी में।"),
        canon=f"{SITE}/sawal",
        crumbs=f'<a href="{SITE}/">कृषि मित्र</a> › किसान के सवाल',
        body=body,
        ld=_ld(_crumb_ld([("कृषि मित्र", f"{SITE}/"),
                          ("किसान के सवाल", f"{SITE}/sawal")])),
        active="", extra_css=_SAWAL_CSS,
    )


@router.get("/sawal/sitemap.xml")
def sawal_sitemap():
    # MUST stay above /sawal/{crop_key} — otherwise the catch-all matches
    # "sitemap.xml" as a crop slug and the sitemap 404s.
    today = datetime.utcnow().strftime("%Y-%m-%d")
    urls = [f"{SITE}/sawal"] + [f"{SITE}/sawal/{s}" for s, _h, _n in crops_with_qa()]
    body = "".join(
        f"<url><loc>{u}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>monthly</changefreq></url>" for u in urls)
    return Response(
        content=('<?xml version="1.0" encoding="UTF-8"?>'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                 f"{body}</urlset>"),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/sawal/{crop_key}", response_class=HTMLResponse)
def sawal_crop(crop_key: str):
    slug = crop_key.lower().strip()
    if slug not in CROPS:
        return _not_found()
    crop_hi = CROPS[slug][1]

    grouped = get_qa(slug)
    # 404 until the crop has enough answers to be worth a page — an
    # unharvested (or barely harvested) crop must not enter the index thin.
    if sum(len(v) for v in grouped.values()) < MIN_QA_TO_PUBLISH:
        return _not_found()

    sections, faqs, n = [], [], 0
    for topic_hi, items in grouped.items():
        cards = []
        for qa in items:
            n += 1
            html, q, a = _qa_card(qa, topic_hi, crop_hi)
            cards.append(html)
            faqs.append((q, a))
        sections.append(f'<h2 class="topic-h">{escape(topic_hi)}</h2>{"".join(cards)}')

    faq_ld = _faq(faqs)[1]
    others = "".join(
        f'<a class="sawal-tile" href="{SITE}/sawal/{s}"><b>{escape(h)}</b>'
        f'<span>{c} सवाल-जवाब</span></a>'
        for s, h, c in crops_with_qa() if s != slug)

    body = f"""<h1>{escape(crop_hi)} की खेती — किसानों के असली सवाल और जवाब</h1>
<p class="sawal-intro">{escape(crop_hi)} पर किसानों ने <strong>किसान कॉल सेंटर
(भारत सरकार)</strong> पर जो सवाल पूछे और कृषि विशेषज्ञों ने जो जवाब दिए, वही यहां
दिए गए हैं — कुल {n} सवाल-जवाब।
<a href="{SITE}/bhav">आज का मंडी भाव देखें →</a></p>
{"".join(sections)}
<p class="sawal-note">⚠️ ये जवाब भारत सरकार के किसान कॉल सेंटर के रिकॉर्ड से लिए गए हैं
और सामान्य जानकारी के लिए हैं। दवा की मात्रा फसल की अवस्था, मिट्टी और मौसम पर निर्भर करती है —
इसलिए छिड़काव से पहले अपने नज़दीकी कृषि अधिकारी या KVK से सलाह ज़रूर लें।</p>
<h2>दूसरी फसलों के सवाल</h2>
<div class="sawal-grid">{others}</div>"""

    return _doc(
        title=f"{crop_hi} की खेती के सवाल-जवाब — किसान कॉल सेंटर | कृषि मित्र",
        desc=(f"{crop_hi} में कीट, रोग, खरपतवार, खाद और किस्मों के {n} असली सवाल — "
              f"किसान कॉल सेंटर (भारत सरकार) पर किसानों को दिए गए जवाब, हिंदी में।"),
        canon=f"{SITE}/sawal/{slug}",
        crumbs=(f'<a href="{SITE}/">कृषि मित्र</a> › '
                f'<a href="{SITE}/sawal">किसान के सवाल</a> › {escape(crop_hi)}'),
        body=body,
        ld=_ld(faq_ld, _crumb_ld([("कृषि मित्र", f"{SITE}/"),
                                  ("किसान के सवाल", f"{SITE}/sawal"),
                                  (crop_hi, f"{SITE}/sawal/{slug}")])),
        active="", extra_css=_SAWAL_CSS,
    )
