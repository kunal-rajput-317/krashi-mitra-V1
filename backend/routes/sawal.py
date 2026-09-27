# ============================================================
# routes/sawal.py
# कृषि मित्र — /sawal, removed 2026-09-28
#
# /sawal published Kisan Call Centre answers as the feed wrote them. That put
# doses on every crop page and pesticides banned in India on five of them:
# phorate (banned since 31 Dec 2020) on /sawal/jowar, and the crop antibiotics
# streptocycline / streptomycin (banned from 1 Jan 2024) on aam, bajra, mirch
# and tamatar — with no safety notice. LEGAL_RULES §2, three ways. The owner
# removed the section. The harvest (services/kcc_service.py) went with it.
#
# Every /sawal URL now answers 410, not 404, so Google drops them instead of
# retrying. Do not bring the section back without a dose filter, the banned
# list and the safety text from services/legal.py over every stored answer.
# ============================================================

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend.routes.bhav import _doc

router = APIRouter()

SITE = "https://krashimitra.in"


@router.api_route("/sawal", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/sawal/{rest:path}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def sawal_gone(rest: str = ""):
    body = ('<div style="max-width:640px;margin:24px auto;padding:18px 20px;'
            'background:var(--white);border:1px solid var(--border);border-radius:12px;'
            'line-height:1.75"><b>यह पेज हटा दिया गया है।</b><br>'
            'फसल की समस्या के लिए सरकारी किसान कॉल सेंटर (टोल-फ्री) '
            '<b>1800-180-1551</b> पर बात करें, या '
            '<a href="/articles/">खेती के लेख</a> देखें।</div>')
    resp = _doc("पेज हटा दिया गया — कृषि मित्र", "यह पेज अब उपलब्ध नहीं है।",
                f"{SITE}/sawal", "", body, active="", robots="noindex, nofollow",
                journey=False)
    resp.status_code = 410
    return resp
