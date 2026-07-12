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

_ARTICLES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "articles"

_PUBLISHED_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_MODIFIED_RE = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')

# slug → {published, modified}, rebuilt when any article file's mtime changes.
_cache: dict = {"stamp": None, "meta": {}}


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
        meta[path.stem] = {
            "published": published,
            # fall back to published so a card always has something to show
            "modified": modified or published,
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
