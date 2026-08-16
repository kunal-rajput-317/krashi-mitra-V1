# ============================================================
# routes/articles.py
# Krishi Mitra — article metadata (published / updated dates)
#
# GET /articles/meta → { "<slug>": {"published": "...", "modified": "..."} }
#
# The dates live in each article's own JSON-LD (`datePublished` /
# `dateModified`) — that file is the single source of truth. We parse them
# straight out of frontend/articles/*.html at request time (mtime-cached,
# same pattern as routes/product.py) so nothing has to be re-run or kept in
# sync by hand: edit an article's date and every card that shows it follows.
#
# The homepage uses this to render "आज / कल / N दिन पहले" labels that are
# computed at view time instead of hardcoded (hardcoded ones silently become
# lies a day later). Cards also carry a baked-in date as a fallback, so the
# section still renders correct dates if this endpoint is unreachable.
# ============================================================

import re
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
_ARTICLES_DIR = _FRONTEND_DIR / "articles"

_PUBLISHED_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_MODIFIED_RE = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')

_OG_IMAGE_RE = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"')
_IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"')

# Chrome that appears in every article and is never the article's subject.
# Both spellings of the assistant icon: it was "AI chat icon.png" (a 1.1 MB
# 1254px PNG drawn into a 62px box on all 89 pages) before it became
# "ai-chat-icon.webp", and a rename must not quietly make it hero-eligible.
_NOT_A_HERO = ("krashimitra_logo", "ai chat icon", "ai-chat-icon",
               "og-banner", "whatsapp_icon", "favicon")

# slug → {published, modified, image}, rebuilt when any article file's mtime changes.
_cache: dict = {"stamp": None, "meta": {}}


def _card_cut(rel: str) -> str:
    """Prefer the 480px card variant of a hero when one sits beside it.

    tools/fetch_article_images.py writes "<name>.webp" (1200×675, for the page
    and og:image) and "<name>-card.webp" (480×270). This endpoint only ever
    feeds card images, and /articles/ renders 79 of them into ~360px-wide bands
    on phones, so the big one would be ~5× the bytes for no visible difference.
    """
    stem, dot, ext = rel.rpartition(".")
    if not stem:
        return rel
    # Test the candidate, not the stem's spelling: "kisan-credit-card" ends in
    # "-card" without being a card cut, so a stem-based guard would leave that
    # article on the full-size file forever.
    card = f"{stem}-card{dot}{ext}"
    return card if card != rel and (_FRONTEND_DIR / card).is_file() else rel


def _hero_image(text: str) -> str | None:
    """The article's own lead image, as a frontend-relative path ("images/…").

    og:image first (that is the article's declared representative image), then
    the first content <img> in the body. The file must actually exist on disk:
    several articles point at images that were never committed, and a missing
    static file is served as the 200-HTML fallback page rather than a 404 — a
    card would show a broken image and we would never hear about it.
    """
    candidates = _OG_IMAGE_RE.findall(text) + _IMG_SRC_RE.findall(text)
    for raw in candidates:
        low = raw.lower()
        if any(skip in low for skip in _NOT_A_HERO):
            continue
        # https://krashimitra.in/images/x.png | ../images/x.png | /images/x.png
        rel = re.sub(r"^https?://[^/]+/", "", raw).lstrip("./").lstrip("/")
        rel = rel.split("?", 1)[0].split("#", 1)[0]
        if not rel.startswith("images/"):
            continue
        if (_FRONTEND_DIR / rel).is_file():
            return _card_cut(rel)
    return None


def _scan() -> dict:
    meta = {}
    for path in sorted(_ARTICLES_DIR.glob("*.html")):
        if path.name == "index.html":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        pub = _PUBLISHED_RE.search(text)
        mod = _MODIFIED_RE.search(text)
        if not (pub or mod):
            continue
        published = pub.group(1)[:10] if pub else None
        modified = mod.group(1)[:10] if mod else None
        # Lowercased stem: the canonical URL, the sitemap and the _redirects
        # targets all use it, so callers keying off a link's slug match here.
        meta[path.stem.lower()] = {
            "published": published,
            # fall back to published so a card always has something to show
            "modified": modified or published,
            # None when the article has no usable image of its own — the card
            # keeps whatever stand-in image is baked into its markup.
            "image": _hero_image(text),
        }
    return meta


def _get_meta() -> dict:
    try:
        stamp = tuple(sorted(
            (p.name, p.stat().st_mtime) for p in _ARTICLES_DIR.glob("*.html")))
    except OSError:
        return _cache["meta"]
    if stamp != _cache["stamp"]:
        scanned = _scan()
        if scanned:                     # keep the last good map if a scan comes back empty
            _cache.update(stamp=stamp, meta=scanned)
    return _cache["meta"]


@router.get("/articles/meta")
def articles_meta():
    return _get_meta()
