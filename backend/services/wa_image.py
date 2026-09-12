# ============================================================
# services/wa_image.py
# तस्वीर — the picture that goes out with the daily channel post.
# ------------------------------------------------------------
# A WhatsApp channel post with a picture is opened; a wall of text is scrolled
# past. That is the whole reason this file exists. But a picture is also the
# easiest place on this page to tell a lie, so the split it draws is the same
# one services/wa_style draws one level up, and it is just as hard a rule:
#
#     THIS MODULE MAKES THE BACKDROP. IT NEVER MAKES A NUMBER.
#
# The prices are drawn ON TOP of whatever comes back from here, by the admin
# page's canvas, from the identical line dicts services/wa_post computed for
# the text. So the figure in the picture and the figure in the caption are the
# same variable, not two renderings of one idea that can drift apart.
#
# WHY THE MODEL IS NEVER ASKED FOR TEXT
# -------------------------------------
# Two independent reasons, either one sufficient:
#
#   1. It cannot spell. Every image model in service today renders Devanagari
#      as broken glyphs — conjuncts fall apart, matras land on the wrong
#      letter, and मध्य प्रदेश comes back as decoration that looks like Hindi to
#      someone who cannot read it and like a mistake to everyone who can. Our
#      followers are the second group.
#   2. A number inside a JPEG cannot be checked. The भरोसा score, the flags,
#      the "same numbers in every format" test — all of it operates on the
#      line dicts. A price the model painted is outside that machinery
#      entirely, and would be the first figure on this page that nothing
#      verifies.
#
# So _NO_TEXT below is appended to EVERY prompt, including one the owner typed
# himself. That is deliberate: asking for lettering is asking for the one thing
# this module must not produce, and the field where he would ask is the field
# that appends the ban.
#
# THREE WAYS TO GET A PROMPT (MODES, below)
#   • scene  — built from today's post: the state, the season the month is in,
#              the crop the post opens on. No price, no direction, no mood
#              standing in for a figure — a sunlit field does not mean prices
#              rose, and a picture that implied it would be a claim.
#   • random — one of a curated set, rotated on the same (state, date) walk
#              services/wa_style uses, so two neighbouring channels do not get
#              the same photograph on the same morning.
#   • custom — whatever the owner types, plus the ban.
#
# GENERATING IS OPTIONAL, AND THE DEFAULT IS NOT TO. With no picture at all the
# panel still draws a complete card — the prices on a brand-coloured ground —
# so a channel is never held up by an API key, a spent quota or a bad morning
# at someone else's service. The state's नक्शा og card was tried in that slot
# and removed: it is a landscape card carrying its own wordmark and its own
# title, so it either got sliced by the portrait crop or put a second lockup
# behind the crop names. The card names the state in 62px type already.
#
# EVERYTHING COMES BACK AS A data: URI, never a URL. The admin page composites
# on a <canvas> and then reads it back with toBlob() to put a PNG on the
# clipboard; a canvas that has drawn a cross-origin image is tainted and
# toBlob() throws. Handing the browser bytes instead of a link is what keeps
# the copy button working.
#
# Runnable manually:  python -m backend.services.wa_image "Madhya Pradesh"
# ============================================================

import base64
import hashlib
import logging
import re
import time
from datetime import date
from pathlib import Path

import httpx

from backend.config import get_setting

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]

# Appended to every prompt, typed or generated. See the header.
_NO_TEXT = (
    "Absolutely no text, no letters, no words, no numbers, no signage, no "
    "watermark and no logo anywhere in the image. Photographic and real, as a "
    "documentary photographer would shoot it - natural light, ordinary working "
    "people photographed with dignity, nothing posed, staged or glossy."
)

# A typed prompt is capped rather than trusted. Long prompts are where the ban
# above gets buried under three paragraphs and quietly stops being obeyed, and
# there is no wording worth having that needs more room than this.
_MAX_PROMPT = 600

# What the model must not be asked to depict. Not a content filter — it is the
# same honesty rule the rest of the panel keeps: the picture may show farming,
# it may not show a claim. A depicted rupee note, a price board or a chart all
# say something the data did not.
_BANNED = re.compile(
    r"\b(text|caption|title|label|word|letter|number|digit|price|rupee|rs\.?|"
    r"signboard|banner|poster|watermark|logo|chart|graph|table|headline)\b|₹",
    re.I)

MODES = [
    {"id": "scene",  "hi": "आज के हिसाब से",
     "note": "आज की पोस्ट से अपने आप — राज्य, महीना, और जिस फसल पर पोस्ट खुलती है।"},
    {"id": "random", "hi": "कुछ भी",
     "note": "तैयार दृश्यों में से एक — हर चैनल को अलग, रोज़ बदलता।"},
    {"id": "custom", "hi": "अपना प्रॉम्प्ट",
     "note": "जो आप लिखें वही बनेगा — बस तस्वीर में कोई अक्षर या अंक नहीं आएगा।"},
]
_MODE_IDS = {m["id"] for m in MODES}

# The season a month sits in, for the scene prompt. Coarse on purpose: India
# has too many local calendars for a table this size to be right everywhere,
# and "post-monsoon, fields still green" is true in more places in October than
# any sharper claim would be.
_SEASON = {
    1:  "cool dry winter morning, rabi crops standing green in the fields",
    2:  "late winter, rabi crops filling out, clear light",
    3:  "rabi harvest under way, dry golden fields, warm haze",
    4:  "peak harvest heat, threshing and stacked produce, dusty golden light",
    5:  "hot pre-monsoon, dry cracked ground, fields being prepared",
    6:  "first monsoon rains arriving, wet dark soil, sowing under way",
    7:  "full monsoon, heavy grey sky, flooded green paddy fields",
    8:  "monsoon, lush deep-green kharif crops, water standing between bunds",
    9:  "late monsoon, kharif crops nearly grown, breaking clouds",
    10: "post-monsoon, kharif harvest beginning, clear soft light",
    11: "early winter, harvest and rabi sowing together, cool morning mist",
    12: "cold winter morning, fog over young rabi crops",
}

# Rotated so a state does not get the same light every day. Carries no claim —
# the hour of the day says nothing about the price, which is exactly why it is
# safe to vary and the weather is not.
_LIGHT = [
    "just after sunrise, long low light",
    "mid-morning, bright and clear",
    "overcast soft even light",
    "late afternoon, warm golden light",
    "the hour before sunset, long shadows",
]

# The curated pool behind "कुछ भी". Every one of them is a scene a farmer in
# this country would recognise as his own week, rather than the stock-photo
# idea of Indian farming — one man, one turban, one impossibly golden field.
_SCENES = [
    "a busy district mandi at dawn, sacks of grain open in rows, traders and "
    "farmers inspecting the produce by hand",
    "a farmer and his wife loading filled sacks onto a tractor trolley at the "
    "edge of a harvested field",
    "hands cupping freshly threshed grain, the field and the heap soft behind",
    "a village weighing scale in use at a collection point, several farmers "
    "waiting their turn",
    "a tractor with a trailer on a narrow field road between two crops, dust "
    "rising behind it",
    "an irrigation channel running into a field, a farmer adjusting the flow "
    "with a spade",
    "a woman winnowing grain in a flat basket, chaff catching the light",
    "a small farm equipment repair yard, a mechanic and a farmer looking at a "
    "pump set together",
    "a bullock cart and a tractor side by side outside a mandi gate in the "
    "morning",
    "a farmer on his phone standing at the edge of his field, the crop "
    "shoulder-high around him",
    "sacks stacked in a cold storage doorway, a worker wheeling one out",
    "a group of farmers sitting on sacks under a mandi shed, talking",
]


def _h(s: str) -> int:
    """Stable across processes — the same reason services/wa_style avoids the
    builtin hash(). A rotation that re-deals itself when Render restarts the
    worker is not a rotation."""
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:8], 16)


# The palette the generated maps use, so a channel card and a नक्शा download
# are recognisably the same brand. Single-sourced from make_state_maps.py's
# line by copy rather than import: that file is a build-time script with a
# playwright dependency and importing it into a web worker to read five hex
# strings would pull Chromium into a 512MB box. A test pins them equal.
PALETTE = {"green_dark": "#1a3c2e", "green_mid": "#2d6a4f",
           "green_light": "#52b788", "green_pale": "#d8f3dc", "amber": "#e9a825"}

_LOGO = _ROOT / "frontend" / "assets" / "krashimitra_logo.png"
_logo_uri: str | None = None


def logo() -> str:
    """The कृषि मित्र emblem as a data: URI, or "" if it is missing.

    Every image this project generates carries the lockup — the नक्शा maps do
    it through make_state_maps.brand_mark(), and the channel card does it by
    drawing this. A card that travels off WhatsApp into a forward with no mark
    on it is a card doing someone else's marketing.

    A data: URI rather than /assets/krashimitra_logo.png because the panel
    draws it onto the same canvas as the picture and then calls toBlob(); one
    cross-origin pixel taints that canvas and the copy button stops working."""
    global _logo_uri
    if _logo_uri is None:
        try:
            _logo_uri = ("data:image/png;base64,"
                         + base64.b64encode(_LOGO.read_bytes()).decode())
        except OSError:
            _logo_uri = ""
    return _logo_uri


def catalog() -> dict:
    """What the panel's mode picker offers, plus what its canvas draws with.

    The logo and the palette ride along here — once per page load — rather than
    on each image call: they are the same bytes for all 31 states, and the
    panel repaints a card every time a dropdown moves."""
    return {"modes": [dict(m) for m in MODES], "scenes": len(_SCENES),
            "logo": logo(), "palette": dict(PALETTE)}


# ── prompts ──────────────────────────────────────────────────

def scene_prompt(post: dict, day: date | None = None) -> str:
    """A prompt built from today's post — state, month, opening crop.

    Deliberately NOT built from the prices. A picture cannot carry "₹2,280, up
    2.8%" honestly, and every attempt to make it try — brighter light when the
    market rose, a heavier sky when it fell — is a claim smuggled past the
    machinery that checks claims. So the figure stays in the overlay, where the
    admin page draws it from the same line dict the caption used, and the
    picture is only ever the place that figure is standing in."""
    day = day or date.today()
    state = (post.get("state") or "").strip() or "north India"
    crops = post.get("crops") or []
    # The ENGLISH commodity name: the model was trained on "soybean", not
    # सोयाबीन, and asking in Devanagari is how you get a picture of wheat.
    crop = (crops[0].get("commodity") if crops else "") or ""
    crop = re.sub(r"\s*\(.*?\)", "", crop).strip().lower()

    season = _SEASON.get(day.month, _SEASON[10])
    light = _LIGHT[(_h(post.get("key") or state) + day.toordinal()) % len(_LIGHT)]

    subject = (f"a {crop} field in {state}, India" if crop
               else f"farmland in {state}, India")
    return (f"{subject}. {season}. {light}. Farmers at work in the frame, "
            f"seen the way a local news photographer would see them.")


def random_prompt(key: str, day: date | None = None) -> str:
    """One of the curated scenes, chosen by the same (key, date) walk the post
    rotation uses — so it is stable across a reload, different from the
    neighbouring channel, and different from yesterday."""
    day = day or date.today()
    i = (_h(key or "x") + day.toordinal()) % len(_SCENES)
    return f"{_SCENES[i]}, rural India."


def build_prompt(post: dict, mode: str = "scene", custom: str = "",
                 day: date | None = None) -> dict:
    """{mode, prompt, full, warnings} — the prompt as typed and as sent.

    `prompt` is what the panel shows and lets the owner edit; `full` is what
    goes to the model, which is `prompt` plus the ban. Keeping the two apart is
    what lets the textarea stay readable without the ban ever being editable.

    A typed prompt that asks for lettering is not refused — the ban is appended
    anyway and the owner is told why it will not appear. A hard refusal here
    would only teach him to phrase it around the filter; the ban is what
    actually holds, and it holds whatever he typed."""
    mode = mode if mode in _MODE_IDS else "scene"
    warnings = []

    if mode == "custom":
        prompt = (custom or "").strip()[:_MAX_PROMPT]
        if not prompt:
            mode, prompt = "scene", scene_prompt(post, day)
            warnings.append("प्रॉम्प्ट खाली था — आज के हिसाब से बना दिया")
        elif _BANNED.search(prompt):
            hits = sorted({m.group(0).lower() for m in _BANNED.finditer(prompt)})
            warnings.append(
                "तस्वीर में अक्षर या अंक नहीं आएंगे — भाव ऊपर से लिखे जाते हैं, "
                f"तस्वीर के अंदर नहीं (आपने लिखा: {', '.join(hits[:4])})")
    elif mode == "random":
        prompt = random_prompt(post.get("key") or post.get("state") or "", day)
    else:
        prompt = scene_prompt(post, day)

    return {"mode": mode, "prompt": prompt,
            "full": f"{prompt} {_NO_TEXT}", "warnings": warnings}


# ── the model ────────────────────────────────────────────────

# Deliberately tiny. The browser is the real store — the admin page holds each
# state's generated picture in a JS variable for the morning — and this exists
# only so a double-click, or a re-render of the same card, does not bill twice.
# Four ~1.5MB data URIs is about as much of a 512MB box as a convenience is
# worth.
_CACHE_MAX = 4
_CACHE_TTL = 3600.0
_cache: dict = {}


def _keys() -> list:
    """The Gemini keys, in order. Shared with the chat pipeline rather than
    re-listed here — a key added for one and not the other is a bug that only
    shows up under quota pressure."""
    from backend.services.chatbot_service import gemini_keys
    return gemini_keys()


def _pick(data: dict) -> str | None:
    """The first inline image in a generateContent response, as a data: URI.

    The image models return the picture as an inlineData part alongside any
    commentary parts, and which position it lands in is not contractual — so
    this walks the parts rather than indexing into them."""
    for cand in (data.get("candidates") or []):
        for part in ((cand.get("content") or {}).get("parts") or []):
            inline = part.get("inlineData") or part.get("inline_data") or {}
            b64 = inline.get("data")
            if b64:
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                return f"data:{mime};base64,{b64}"
    return None


async def generate(full_prompt: str) -> dict:
    """{image, cached, model} for a prompt, or raises with a readable reason.

    Tries every configured key in turn, exactly as the chat pipeline does: the
    image quota is small and per-key, and a morning of 31 states will walk off
    the end of the first one."""
    model = get_setting("gemini_image_model", "gemini-2.5-flash-image")
    timeout = float(get_setting("gemini_image_timeout", 60.0))

    ck = hashlib.md5(f"{model}|{full_prompt}".encode("utf-8")).hexdigest()
    hit = _cache.get(ck)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return {"image": hit[1], "cached": True, "model": model}

    keys = _keys()
    if not keys:
        raise RuntimeError("कोई GEMINI_API_KEY सेट नहीं है — AI तस्वीर नहीं बन सकती। "
                           "नक्शे वाला मुफ़्त बैकड्रॉप अब भी चलेगा।")

    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    last = None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    async with httpx.AsyncClient(timeout=timeout) as client:
        for name, api_key in keys:
            try:
                r = await client.post(url, json=payload,
                                      headers={"x-goog-api-key": api_key})
                if r.status_code in (429, 403):
                    log.info("[wa_image] %s: %s — next key", name, r.status_code)
                    last = f"{name}: {r.status_code}"
                    continue
                r.raise_for_status()
                uri = _pick(r.json())
                if not uri:
                    last = f"{name}: कोई तस्वीर नहीं लौटी"
                    continue
                if len(_cache) >= _CACHE_MAX:
                    _cache.pop(next(iter(_cache)), None)
                _cache[ck] = (time.time(), uri)
                log.info("[wa_image] OK %s (%s)", name, model)
                return {"image": uri, "cached": False, "model": model}
            except httpx.TimeoutException:
                last = f"{name}: {timeout:g}s में जवाब नहीं आया"
            except Exception as e:                       # noqa: BLE001
                last = f"{name}: {e}"
    raise RuntimeError(f"तस्वीर नहीं बन पाई — {last}")


if __name__ == "__main__":  # pragma: no cover
    import sys
    from backend.services import wa_post

    st = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "Uttar Pradesh"
    p = wa_post.post_for(st)
    if not p:
        print("no post for that state")
        raise SystemExit(1)
    for m in MODES:
        b = build_prompt(p, m["id"],
                         custom="wheat field with the price written on a board")
        print(f"\n===== {m['id']} =====\n{b['prompt']}")
        for w in b["warnings"]:
            print("  ! " + w)
