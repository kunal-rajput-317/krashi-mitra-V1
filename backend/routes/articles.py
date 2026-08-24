# ============================================================
# routes/articles.py
# Krishi Mitra — article metadata (published / updated dates) + article pages
#
# GET /articles/meta   → { "<slug>": {"published": "...", "modified": "..."} }
# GET /articles/<slug> → the page (see the second half of this file)
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

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

log = logging.getLogger(__name__)

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


# ── the article page itself ────────────────────────────────────────────────
#
# Netlify serves the 98 committed articles as static files and never asks us.
# This route exists for the ones that were never committed: an article written
# in the admin panel lives in Postgres, is laid down in frontend/articles/ at
# boot, and has no file on Netlify's disk — so /articles/<slug> falls through
# its redirect rules to the backend proxy and lands here.
#
# It also makes extensionless article URLs work on the backend at all, which
# they never did: StaticFiles does not try "<path>.html", so /articles/foo was
# a 404 in local dev while working perfectly in production. Anything that only
# breaks on localhost gets debugged eventually — at the worst moment.

_ARTICLE_CACHE = {
    # 5 min in the browser, 30 min at Netlify's edge with a day of
    # stale-while-revalidate. Same reasoning as bhav.py's headers: a proxied
    # response is only cached when the origin opts in, and Googlebot crawling
    # through Render's cold starts is what caps how fast a page gets indexed.
    "Cache-Control": "public, max-age=300",
    "Netlify-CDN-Cache-Control":
        "public, durable, max-age=1800, stale-while-revalidate=86400",
}


def _serve(path: Path) -> HTMLResponse:
    return HTMLResponse(path.read_text(encoding="utf-8"), headers=_ARTICLE_CACHE)


@router.get("/articles/{slug}")
def article_page(slug: str):
    # One URL per article: the canonical is the lowercase extensionless form,
    # and sitemap.py serves every article at stem.lower(). Netlify already 301s
    # the .html form for committed articles; panel-published ones have no such
    # rule, so the redirect has to live here too or the page would answer at
    # two URLs and split its own signals.
    canon = slug[:-5] if slug.lower().endswith(".html") else slug
    canon = canon.lower()
    if canon in ("index", ""):
        return RedirectResponse("/articles/", status_code=301)
    if canon != slug:
        return RedirectResponse(f"/articles/{canon}", status_code=301)

    path = _ARTICLES_DIR / f"{slug}.html"
    if path.is_file():
        return _serve(path)

    # Missing file, live row: the boot restore did not run or failed, and this
    # URL is 404ing right now. Lay it down and answer — being self-healing here
    # is worth more than being tidy, because the alternative is a soft-404 in
    # Google's index for however long it takes anyone to notice.
    try:
        from backend.database.db import SessionLocal
        from backend.services import article_publish as ap
        db = SessionLocal()
        try:
            row = ap.get(db, slug)
            if row is not None and row.status == "live":
                log.warning("[articles] %s was missing on disk — re-laid from DB", slug)
                return _serve(ap.materialize(row))
        finally:
            db.close()
    except Exception as e:                      # never turn a 404 into a 500
        log.warning("[articles] DB lookup for %s failed: %s", slug, e)

    fallback = _FRONTEND_DIR / "404.html"
    if fallback.is_file():
        return HTMLResponse(fallback.read_text(encoding="utf-8"), status_code=404)
    raise HTTPException(404, "article not found")
