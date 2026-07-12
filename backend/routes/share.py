# ============================================================
# routes/share.py
# Krishi Mitra — Rich link previews for shared mandi links
#
# WhatsApp/Facebook/Telegram crawlers read OG tags from the first
# 200 response and do NOT follow meta-refresh, so this page carries
# the crop-specific preview while humans get bounced to mandi.html.
# Reached via the Netlify proxy rule /share/* → backend.
# ============================================================

import re
from html import escape
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.services.mandi_service import get_mandi_prices
from backend.database.db import BazarPost, User, UserProfile, get_db

router = APIRouter()

SITE = "https://krashimitra.in"
BACKEND = "https://krashi-mitra-v1.onrender.com"

# commodity keyword → (Wikimedia file, md5 prefix)
# mirrors COMMODITY_TILES in frontend/mandi.html
_TILES = [
    (("wheat",),                    "Wheat close-up.JPG",                        "b4"),
    (("paddy", "dhan", "rice"),     "Rice_grains_(IRRI).jpg",                    "ba"),
    (("onion",),                    "Onion on White.JPG",                        "25"),
    (("potato",),                   "Patates.jpg",                               "ab"),
    (("tomato",),                   "Bright red tomato and cross section02.jpg", "88"),
    (("maize", "corn"),             "Corncobs.jpg",                              "7d"),
    (("soyabean", "soybean"),       "Soybean.USDA.jpg",                          "82"),
    (("gram", "chana", "bengal"),   "Chickpea.jpg",                              "3d"),
    (("mustard", "rai", "sarson"),  "BrownMustardSeed.JPG",                      "ef"),
    (("garlic",),                   "Garlic.jpg",                                "22"),
    (("chilli", "chili", "mirch"),  "Red Chili Pepper.jpg",                      "2a"),
    (("turmeric",),                 "Turmeric-powder.jpg",                       "0a"),
    (("groundnut",),                "Groundnut (Arachis hypogaea).jpg",          "0e"),
    (("bajra", "pearl millet"),     "Bajra.JPG",                                 "49"),
    (("arhar", "tur", "red gram"),  "Toor dal.jpg",                              "de"),
    (("urad", "black gram"),        "Vigna mungo.jpg",                           "e2"),
    (("moong", "green gram"),       "Mung beans.jpg",                            "5e"),
    (("sugarcane",),                "Sugar cane.jpg",                            "cb"),
    (("cotton",),                   "CottonPlant.JPG",                           "68"),
    (("lentil", "masur", "masoor"), "Lentil.jpg",                                "9d"),
    (("peas", "pea"),               "Green peas.jpg",                            "a7"),
    (("brinjal",),                  "Aubergine.jpg",                             "fb"),
    (("cauliflower",),              "Cauliflower.jpg",                           "7c"),
    (("ginger",),                   "Ginger root.jpg",                           "cf"),
]

_FALLBACK_IMAGE = f"{SITE}/images/og-banner.jpg"


# Wikimedia only serves whitelisted thumb widths (https://w.wiki/GHai) —
# verified working: 330, 500, 960, 1280. Anything else returns HTTP 400.
_ALLOWED_WIDTHS = (330, 500, 960, 1280)

# Thumbs wider than the original also 400 — originals narrower than 960px
# (checked via the Commons imageinfo API); everything else is ≥ 960 wide.
_MAX_ORIG_WIDTH = {
    "Chickpea.jpg":     350,
    "Soybean.USDA.jpg": 640,
    "Aubergine.jpg":    681,
    "Cauliflower.jpg":  909,
}


def _crop_image(commodity: str, width: int = 330) -> str:
    """Photo for a commodity, matched on WHOLE WORDS and by the MOST SPECIFIC
    keyword. Plain substring matching gave "Turnip" the अरहर photo ("tur") and
    "Peach"/"Pear" the मटर photo ("pea"); first-tile-wins gave "Green Gram(Moong)"
    the चना photo, because the generic "gram" tile is listed before "green gram"."""
    cl = (commodity or "").lower()
    best, best_len = None, 0
    for keys, file, h in _TILES:
        for k in keys:
            if re.search(rf"\b{re.escape(k)}\b", cl) and len(k) > best_len:
                best, best_len = (file, h), len(k)
    if best:
        file, h = best
        cap = min(width, _MAX_ORIG_WIDTH.get(file, 10**6))
        w = max([a for a in _ALLOWED_WIDTHS if a <= cap] or [330])
        n = quote(file.replace(" ", "_"))
        return (
            "https://upload.wikimedia.org/wikipedia/commons/thumb/"
            f"{h[0]}/{h}/{n}/{w}px-{n}"
        )
    return _FALLBACK_IMAGE


# Hindi crop names used by Krashi Bazar chips → English keyword for _crop_image()
_HI_CROP_EN = {
    "गेहूं": "wheat", "धान": "paddy", "सोयाबीन": "soybean", "प्याज": "onion",
    "आलू": "potato", "टमाटर": "tomato", "मक्का": "maize", "सरसों": "mustard",
    "चना": "chana", "गन्ना": "sugarcane", "लहसुन": "garlic", "मिर्च": "chilli",
    "हल्दी": "turmeric", "मूंगफली": "groundnut", "अरहर": "arhar", "उड़द": "urad",
    "मूंग": "moong", "कपास": "cotton", "मसूर": "masur", "मटर": "peas",
    "बैंगन": "brinjal", "अदरक": "ginger",
}


@router.get("/share/bazar/{post_id}", response_class=HTMLResponse)
def share_bazar(post_id: int, db: Session = Depends(get_db)):
    """OG preview card for a Krashi Bazar post — photo + price + details."""
    target = f"{SITE}/krashi_bajar.html?post={post_id}"

    title = "कृषि बाज़ार — किसान से सीधे खरीदें व बेचें | कृषि मित्र"
    desc  = "फसल की फोटो/वीडियो, सीधा भाव और ऑफर — सीधे किसान से जुड़ें। KrashiMitra पर देखें।"
    image = _FALLBACK_IMAGE

    try:
        post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
        if post:
            user    = db.query(User).filter(User.id == post.user_id).first()
            profile = db.query(UserProfile).filter(UserProfile.user_id == post.user_id).first()

            name = (profile.name if profile and profile.name
                    else (user.name if user else "किसान"))
            tick = " ✅" if user and user.seller_verified else ""
            verb = "बेचना है" if post.post_type == "sell" else "खरीदना है"

            bits = [post.crop or "फसल", verb]
            if post.price:
                bits.append(f"₹{post.price:g}/{post.unit or 'क्विंटल'}")
            title = " — ".join(bits) + " | कृषि बाज़ार"

            dparts = []
            if post.quantity:
                dparts.append(f"📦 {post.quantity:g} {post.unit or 'क्विंटल'} उपलब्ध")
            if post.location:
                dparts.append(f"📍 {post.location}")
            dparts.append(f"🧑‍🌾 {name}{tick}")
            snippet = (post.text or "").strip()
            if snippet:
                dparts.append(snippet[:120] + ("…" if len(snippet) > 120 else ""))
            desc = " · ".join(dparts)

            if post.media_url and post.media_type == "image":
                image = f"{BACKEND}{post.media_url}"
            elif post.crop:
                en = _HI_CROP_EN.get(post.crop.strip(), post.crop)
                image = _crop_image(en, 960)
    except Exception:
        pass  # fall back to generic preview

    t, d, u, i = escape(title), escape(desc), escape(target), escape(image)

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="utf-8">
  <title>{t}</title>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
  <meta property="og:title" content="{t}">
  <meta property="og:description" content="{d}">
  <meta property="og:image" content="{i}">
  <meta property="og:url" content="{u}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{t}">
  <meta name="twitter:description" content="{d}">
  <meta name="twitter:image" content="{i}">
  <meta name="robots" content="noindex">
  <meta http-equiv="refresh" content="0;url={u}">
  <script>location.replace({target!r});</script>
</head>
<body>
  <p><a href="{u}">कृषि बाज़ार पर देखें →</a></p>
</body>
</html>""")


@router.get("/share/mandi", response_class=HTMLResponse)
def share_mandi(state: str = "", commodity: str = "", district: str = ""):
    params = [("state", state), ("commodity", commodity), ("district", district)]
    target = f"{SITE}/mandi.html?" + urlencode([(k, v) for k, v in params if v])

    title = f"{commodity or 'मंडी भाव'} — आज का मंडी भाव | कृषि मित्र"
    desc = "ताजा मंडी भाव, रुझान और सरकारी दरें — कृषि मित्र, किसान का डिजिटल साथी"

    try:
        data = get_mandi_prices(commodity, district, state)
        prices = (data or {}).get("prices") or []
        if prices:
            p = prices[0]
            modal = p.get("modal_price")
            if modal and modal != "-":
                title = f"{p.get('commodity', commodity)}: ₹{modal}/क्विंटल"
                try:
                    pct = float(p.get("change_pct"))
                    if pct:
                        arrow = "▲" if pct > 0 else "▼"
                        sign = "+" if pct > 0 else ""
                        title += f" ({arrow} {sign}{pct:g}% कल से)"
                except (TypeError, ValueError):
                    pass
                desc = (
                    f"🏪 {p.get('market', '-')} · 📍 {p.get('district', '-')} · "
                    f"📅 {p.get('date', '-')} — ताजा भाव कृषि मित्र पर देखें"
                )
    except Exception:
        pass  # preview falls back to the generic title/description

    # 960px → WhatsApp renders the large preview card (≥300px each side);
    # at the default 330px it falls back to the small square thumbnail.
    image = _crop_image(commodity, 960)
    t, d, u, i = escape(title), escape(desc), escape(target), escape(image)

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="utf-8">
  <title>{t}</title>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
  <meta property="og:title" content="{t}">
  <meta property="og:description" content="{d}">
  <meta property="og:image" content="{i}">
  <meta property="og:url" content="{u}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{t}">
  <meta name="twitter:description" content="{d}">
  <meta name="twitter:image" content="{i}">
  <meta name="robots" content="noindex">
  <meta http-equiv="refresh" content="0;url={u}">
  <script>location.replace({target!r});</script>
</head>
<body>
  <p><a href="{u}">ताजा मंडी भाव देखें →</a></p>
</body>
</html>""")
