"""
KrashiMitra — Festival Wishes Management Router
Allows admin to manage festival greetings, custom image, duration, and blessings.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/festival", tags=["Festival Wishes"])

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = BASE_DIR / "backend" / "data" / "festival_config.json"
FESTIVAL_IMG_DIR = BASE_DIR / "frontend" / "images" / "festivals"
FESTIVAL_IMG_DIR.mkdir(parents=True, exist_ok=True)

# Default configuration fallback
DEFAULT_CONFIG = {
    "active": True,
    "festival_id": "krishna_janmashtami",
    "festival_name": "श्री कृष्ण जन्माष्टमी",
    "top_pill": "🪶 ॥ हरे कृष्ण हरे राम ॥ 🪈",
    "title": "श्री कृष्ण जन्माष्टमी की हार्दिक शुभकामनाएं",
    "blessing_summary": "कृषि मित्र परिवार की ओर से आपको एवं आपके पूरे परिवार को पावन पर्व की कोटि-कोटि मंगलकामनाएं!",
    "bullet_1": "भगवान श्री कृष्ण का आशीर्वाद आपके खेत-खलिहान में लहलहाती फसल और समृद्धि लाए।",
    "bullet_2": "गौमाता और पशुधन सदैव स्वस्थ रहें एवं घर-आंगन में सुख-शांति बनी रहे।",
    "image_url": "/images/krishna-janmashtami.webp",
    "cta_text": "🙏 जय श्री कृष्ण (शुभकामनाएं स्वीकारें)",
    "start_time": "2026-09-04T00:00:00+05:30",
    "end_time": "2026-09-05T23:59:59+05:30",
    "cooldown_hours": 3,
    "updated_at": "2026-09-04T15:10:00+05:30",
}


def _load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading festival config: {e}")
    return DEFAULT_CONFIG.copy()


def _save_config(config: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _is_active_now(config: dict) -> bool:
    if not config.get("active", False):
        return False

    start_str = config.get("start_time")
    end_str = config.get("end_time")

    now = datetime.now(timezone.utc)

    # Convert start/end to datetime objects
    try:
        if start_str:
            start_dt = datetime.fromisoformat(start_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            if now < start_dt:
                return False
    except Exception:
        pass

    try:
        if end_str:
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            if now > end_dt:
                return False
    except Exception:
        pass

    return True


class FestivalConfigRequest(BaseModel):
    active: bool
    festival_id: Optional[str] = "custom_festival"
    festival_name: str
    top_pill: Optional[str] = "✨ मंगलकामनाएं ✨"
    title: str
    blessing_summary: str
    bullet_1: Optional[str] = ""
    bullet_2: Optional[str] = ""
    image_url: str
    cta_text: Optional[str] = "🙏 शुभकामनाएं स्वीकारें"
    start_time: str
    end_time: str
    cooldown_hours: Optional[int] = 3


class GenerateFestiveImageRequest(BaseModel):
    festival_name: str
    theme_prompt: Optional[str] = ""


@router.get("/config")
def get_festival_config():
    """Returns the current festival popup configuration and active status."""
    config = _load_config()
    is_live = _is_active_now(config)
    return {
        "success": True,
        "is_live": is_live,
        "config": config,
    }


@router.post("/config")
def update_festival_config(payload: FestivalConfigRequest):
    """Updates the festival configuration from admin panel."""
    current = _load_config()
    data = payload.dict()
    data["updated_at"] = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
    current.update(data)
    _save_config(current)
    
    is_live = _is_active_now(current)
    return {
        "success": True,
        "message": "त्योहार शुभकामनाएं सेटिंग्स सफलतापूर्वक सहेज दी गईं!",
        "is_live": is_live,
        "config": current,
    }


@router.post("/upload-image")
async def upload_festival_image(file: UploadFile = File(...)):
    """Uploads a festival image from the admin panel."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="कोई फ़ाइल नहीं मिली")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        ext = ".webp"

    clean_stem = re.sub(r"[^\w\-]", "_", Path(file.filename).stem)[:30]
    filename = f"fest_{clean_stem}_{int(time.time())}{ext}"
    dest_path = FESTIVAL_IMG_DIR / filename

    try:
        contents = await file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)

        # Optimize to webp if possible
        webp_name = f"fest_{clean_stem}_{int(time.time())}.webp"
        webp_path = FESTIVAL_IMG_DIR / webp_name
        try:
            from PIL import Image
            with Image.open(dest_path) as img:
                img.save(webp_path, "WEBP", quality=88)
            relative_url = f"/images/festivals/{webp_name}"
        except Exception:
            relative_url = f"/images/festivals/{filename}"

        return {
            "success": True,
            "message": "फोटो सफलतापूर्वक अपलोड हो गई!",
            "image_url": relative_url,
        }
    except Exception as e:
        logger.error(f"Festival image upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"अपलोड विफल: {str(e)}")


@router.post("/generate-image")
async def generate_festive_image(payload: GenerateFestiveImageRequest):
    """Generates an AI festive image using Gemini/call_ai + Google Imagen 3 / Pollinations cascade."""
    import base64
    import io
    import urllib.parse
    import httpx
    from PIL import Image
    from backend.services.chatbot_service import call_ai

    festival = payload.festival_name.strip() or "भारतीय कृषि व त्योहार"
    custom_desc = payload.theme_prompt.strip()

    # Step 1: Synthesize prompt via Gemini / call_ai
    ai_prompt_query = f"""
Write an exquisite, photorealistic image prompt (in English, max 45 words) for an Indian festival celebrating: '{festival}'.
Context: {custom_desc or 'Traditional Indian festive celebration, lush agricultural fields, happy Indian farming family, vibrant auspicious colors, divine diyas/flowers, 4k photorealistic, golden hour lighting, 4:3 aspect ratio'}.
Requirements: Realistic photography, warm atmospheric lighting, divine traditional celebration. NO text, NO watermarks, NO letters.
Output ONLY the raw prompt text with no quotes or explanation.
"""
    detailed_prompt = ""
    try:
        res, _ = await call_ai(ai_prompt_query, max_tokens=100)
        if res:
            cleaned = res.strip().replace('"', '').replace('\n', ' ')
            if len(cleaned) >= 15 and not any(b in cleaned.lower() for b in ["i cannot", "sorry", "unavailable"]):
                detailed_prompt = cleaned
    except Exception as ge:
        logger.warning(f"Gemini festival prompt synthesis fallback: {ge}")

    if not detailed_prompt:
        detailed_prompt = f"Splendid divine Indian festival celebration of {festival}, golden glowing diyas, marigold garlands, sacred rural temple and blooming fields, hyperrealistic 4K, warm atmospheric lighting, 4:3 aspect ratio"

    filename = f"fest_ai_{int(time.time())}.webp"
    local_path = FESTIVAL_IMG_DIR / filename

    # Step 2: Try Google Imagen 3 if keys available
    for env_k in ["GEMINI_API_KEY", "GEMINI_API_KEY2", "GEMINI_API_KEY3"]:
        api_k = os.getenv(env_k, "").strip()
        if not api_k:
            continue
        try:
            imagen_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_k}"
            payload_data = {
                "instances": [{"prompt": detailed_prompt}],
                "parameters": {"sampleCount": 1, "aspectRatio": "4:3"}
            }
            async with httpx.AsyncClient(timeout=22.0) as client:
                resp = await client.post(imagen_url, json=payload_data)
                if resp.status_code == 200:
                    data = resp.json()
                    preds = data.get("predictions", [])
                    if preds and "bytesBase64Encoded" in preds[0]:
                        img_bytes = base64.b64decode(preds[0]["bytesBase64Encoded"])
                        # Save & optimize as webp
                        with Image.open(io.BytesIO(img_bytes)) as img:
                            img.save(local_path, "WEBP", quality=90)
                        return {
                            "success": True,
                            "message": f"Google Imagen 3 से {festival} की AI फोटो तैयार हो गई!",
                            "image_url": f"/images/festivals/{filename}",
                            "prompt": detailed_prompt,
                            "source": "google_imagen_3"
                        }
        except Exception as ie:
            logger.warning(f"Imagen 3 festival generation attempt on {env_k} error: {ie}")

    # Step 3: Try Pollinations AI Flux engine
    try:
        encoded_p = urllib.parse.quote(detailed_prompt)
        seed = int(time.time())
        poll_url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=800&height=600&model=flux&nologo=true&seed={seed}"
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            resp = await client.get(poll_url, headers={"User-Agent": "Mozilla/5.0 (KrashiMitra Festival AI Generator)"})
            if resp.status_code == 200 and len(resp.content) > 6000:
                with Image.open(io.BytesIO(resp.content)) as img:
                    img.save(local_path, "WEBP", quality=88)
                return {
                    "success": True,
                    "message": f"Flux AI से {festival} की मनमोहक फोटो तैयार हो गई!",
                    "image_url": f"/images/festivals/{filename}",
                    "prompt": detailed_prompt,
                    "source": "pollinations_flux"
                }
    except Exception as pe:
        logger.warning(f"Pollinations festival image generation failed: {pe}")

    # Step 4: Fallback to default
    return {
        "success": True,
        "message": "डिफ़ॉल्ट उत्सव फोटो चुनी गई",
        "image_url": "/images/krishna-janmashtami.webp",
        "prompt": detailed_prompt,
        "source": "fallback"
    }
