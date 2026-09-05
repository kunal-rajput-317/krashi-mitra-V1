# ============================================================
# routes/credits.py
# KrashiMitra — image credits  (GET /articles/credits)
#
# The article photographs are self-hosted copies of Wikimedia Commons files.
# Most are CC BY or CC BY-SA, which permit exactly this — including on a site
# that carries ads — on the condition that the author, the licence and the fact
# that we modified the file are all stated. This page is that statement.
#
# It is rendered from frontend/images/articles/CREDITS.json at request time, the
# same file tools/fetch_article_images.py writes when it downloads an image. Add
# an image and its credit appears here on the next page view — there is no list
# to remember to update, and no way to publish a photograph whose credit is
# missing without it being visible here.
#
# noindex: it exists to satisfy the licences and for a reader who wants the
# provenance, not to compete with the articles in search.
# ============================================================

import json
from html import escape
from pathlib import Path

from fastapi import APIRouter

from backend.routes.bhav import _doc, _ld

router = APIRouter()

SITE = "https://krashimitra.in"
_IMAGES = Path(__file__).resolve().parents[2] / "frontend" / "images"
_CREDITS = _IMAGES / "articles" / "CREDITS.json"
# The /rental machine photographs are the same deal from the same place —
# Commons files, mostly CC BY / CC BY-SA, self-hosted. They are listed on THIS
# page rather than one of their own because the obligation is identical and a
# second credits page is a second thing to remember to link.
_RENTAL_CREDITS = _IMAGES / "rental" / "CREDITS.json"
# The crop photographs behind the mandi grid thumbnails and the og:image on
# every share card. Until 2026-09-04 these were the one set that was still
# hotlinked from upload.wikimedia.org with no credit anywhere — and eleven of
# them were under licences an ad-supported site may not use at all. They are
# now self-hosted like the other two sets, so they are credited like them.
_CROP_CREDITS = _IMAGES / "crops" / "CREDITS.json"

_cache: dict = {"mtime": None, "rows": []}

_EXTRA_CSS = """
    .cred-intro { margin: 0 0 18px; line-height: 1.75; color: var(--ink-soft); }
    .cred-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
    .cred-item {
      display: grid; grid-template-columns: 96px 1fr; gap: 12px; align-items: center;
      background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 10px;
    }
    .cred-item img { width: 96px; height: 54px; object-fit: cover; border-radius: 7px; display: block; }
    .cred-meta { min-width: 0; font-size: 13px; line-height: 1.55; }
    .cred-meta b { display: block; font-size: 13.5px; }
    .cred-meta a { color: var(--green-dark); }
    .cred-lic { color: var(--ink-soft); font-size: 12px; }
    @media (max-width: 480px) {
      .cred-item { grid-template-columns: 72px 1fr; }
      .cred-item img { width: 72px; height: 41px; }
    }
"""


def _rental_rows() -> list[dict]:
    """Credits for the /rental machine photographs.

    Same shape the article rows use, so the page renders one list. A credit
    whose .webp is not on disk is skipped for the article set's reason: the
    entry describes a file we are publishing, and one we are not needs no
    attribution.
    """
    try:
        data = json.loads(_RENTAL_CREDITS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = []
    for name, c in sorted(data.items()):
        if not (_RENTAL_CREDITS.parent / f"{name}.webp").is_file():
            continue
        rows.append({
            "name": name,
            "section": "किराये की मशीनें",
            "thumb": f"images/rental/{name}.webp",
            "file": c.get("file", ""),
            "source": c.get("descriptionurl", ""),
            "author": c.get("author", "unknown"),
            "licence": c.get("licence", ""),
            "licence_url": c.get("licence_url", ""),
        })
    return rows


def _crop_rows() -> list[dict]:
    """Credits for the mandi/share crop photographs. Same shape as the others."""
    try:
        data = json.loads(_CROP_CREDITS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = []
    for name, c in sorted(data.items()):
        if not (_CROP_CREDITS.parent / f"{name}.webp").is_file():
            continue
        rows.append({
            "name": name,
            "section": "फसल चित्र",
            "thumb": f"images/crops/{name}.webp",
            "file": c.get("file", ""),
            "source": c.get("descriptionurl", ""),
            "author": c.get("author", "unknown"),
            "licence": c.get("licence", ""),
            "licence_url": c.get("licence_url", ""),
        })
    return rows


def _rows() -> list[dict]:
    """Credits, newest file state. Re-read only when CREDITS.json changes."""
    def _stamp(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    # Either file changing must re-read both — a single mtime would leave a
    # newly added machine photo uncredited until an article happened to change.
    mtime = (_stamp(_CREDITS), _stamp(_RENTAL_CREDITS), _stamp(_CROP_CREDITS))
    if not any(mtime):
        return _cache["rows"]
    if mtime != _cache["mtime"]:
        try:
            data = json.loads(_CREDITS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        rows = _rental_rows() + _crop_rows()
        for name, c in sorted(data.items()):
            # Only heroes and in-body illustrations are recorded here — the
            # 480px card cuts never get their own credit entry. Do NOT filter on
            # a "-card" suffix: kisan-credit-card and mitti-jaanch-soil-health-
            # card are article slugs that end that way, and a name-based guard
            # drops exactly the two photographs it must not.
            if not (_CREDITS.parent / f"{name}.webp").is_file():
                continue
            rows.append({
                "name": name,
                "section": "लेख",
                "thumb": f"images/articles/{name}-card.webp"
                         if (_CREDITS.parent / f"{name}-card.webp").is_file()
                         else f"images/articles/{name}.webp",
                "file": c.get("file", ""),
                "source": c.get("descriptionurl", ""),
                "author": c.get("author", "unknown"),
                "licence": c.get("licence", ""),
                "licence_url": c.get("licence_url", ""),
            })
        rows.sort(key=lambda r: (r["section"], r["name"]))
        _cache.update(mtime=mtime, rows=rows)
    return _cache["rows"]


@router.get("/articles/credits")
def credits_page():
    rows = _rows()

    items = []
    for r in rows:
        lic = escape(r["licence"])
        if r["licence_url"]:
            lic = f'<a href="{escape(r["licence_url"])}" rel="license nofollow noopener" target="_blank">{lic}</a>'
        src = escape(r["file"]) or r["name"]
        if r["source"]:
            src = (f'<a href="{escape(r["source"])}" rel="nofollow noopener" '
                   f'target="_blank">{src}</a>')
        items.append(
            f'<li class="cred-item">'
            f'<img src="{SITE}/{r["thumb"]}" alt="" loading="lazy" decoding="async" width="96" height="54">'
            f'<div class="cred-meta"><b>{src}</b>'
            f'<span>{escape(r["author"])}</span><br>'
            f'<span class="cred-lic">{lic} — आकार बदला गया व WebP में परिवर्तित</span>'
            f'</div></li>')

    body = (
        '<h1>चित्र स्रोत और श्रेय</h1>'
        '<p class="cred-intro">कृषि मित्र के लेखों और किराये की मशीनों के पेजों पर इस्तेमाल हुई तस्वीरें '
        '<a href="https://commons.wikimedia.org/" rel="nofollow noopener" target="_blank">'
        'Wikimedia Commons</a> से ली गई हैं और हमारे अपने सर्वर से दिखाई जाती हैं। '
        'लेख की तस्वीरें 1200×675 पर और मशीनों की तस्वीरें 400×300 पर काटी गई हैं, '
        'और सभी WebP में बदली गई हैं। '
        'नीचे हर तस्वीर का मूल फ़ाइल नाम, बनाने वाले का नाम और लाइसेंस दिया गया है, '
        'जैसा कि उन लाइसेंस की शर्तें माँगती हैं।</p>'
        f'<ul class="cred-list">{"".join(items)}</ul>'
    )

    canon = f"{SITE}/articles/credits"
    return _doc(
        title="चित्र स्रोत और श्रेय — कृषि मित्र",
        desc="कृषि मित्र के लेखों में इस्तेमाल हुई तस्वीरों के मूल स्रोत, "
             "फ़ोटोग्राफ़र और लाइसेंस की पूरी सूची।",
        canon=canon,
        crumbs=f'<a href="{SITE}/">मुख्य</a> › <a href="{SITE}/articles/">लेख</a> › चित्र स्रोत',
        body=body,
        ld=_ld({"@context": "https://schema.org", "@type": "WebPage",
                "@id": canon, "url": canon, "name": "चित्र स्रोत और श्रेय"}),
        active="",
        extra_css=_EXTRA_CSS,
        robots="noindex, follow",
    )
