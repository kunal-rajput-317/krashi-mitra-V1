# ============================================================
# KrashiMitra — article hero images
#
# Articles used to hotlink Wikimedia Commons directly
# (commons.wikimedia.org/wiki/Special:FilePath/X.jpg?width=480). That was wrong
# in three ways:
#   1. six of those files had been renamed or deleted on Commons and were
#      rendering as broken-image icons on live pages,
#   2. Commons rate-limits (a 429 showed up while auditing 25 URLs — which is
#      exactly what one phone loading /articles/ sends), and
#   3. hotlinking drops the licence attribution the images are given under.
#
# So the images are fetched once, converted to WebP, and served from our own
# origin, with the licence and author recorded next to them.
#
#   python tools/fetch_article_images.py            # fetch what is missing
#   python tools/fetch_article_images.py --force    # re-fetch everything
#   python tools/fetch_article_images.py --verify   # check sources still exist
#
# The manifest is tools/article_images.py. Attribution lands in
# frontend/images/articles/CREDITS.json and is rendered on /articles/credits.
# ============================================================

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "frontend" / "images" / "articles"
CREDITS = OUT_DIR / "CREDITS.json"

API = "https://commons.wikimedia.org/w/api.php"
UA = "KrashiMitra/1.0 (https://krashimitra.in; krashimitra038@gmail.com)"

# Every hero comes out at exactly 1200×675. The figure and the card band are
# both fixed-ratio boxes, so a portrait source would either be cropped to a
# sliver by object-fit or — where height resolves to auto — render as a
# full-height column that shoves the article off the screen. Normalising here
# means the <img width/height> we emit is always the true size of the file, so
# there is no layout shift while it loads.
TARGET_W = 1200
TARGET_H = 675
CARD_W = 480
CARD_H = 270
WEBP_QUALITY = 82

# Below this the upscale to 1200 is visible. Commons has plenty of alternatives;
# fail loudly rather than ship a soft hero.
MIN_SOURCE_W = 900


def _api(params: dict, attempts: int = 4) -> dict:
    """One Commons API call, retried on transient failure.

    A --verify run now makes ~100 of these back to back, and Commons answers
    the odd one with a 500 or a 429. Without a retry a single hiccup aborts the
    whole check, which reads exactly like "the file is gone" — the one thing
    this tool exists to tell you accurately.
    """
    for i in range(attempts):
        try:
            r = requests.get(API, params={**params, "format": "json"},
                             headers={"User-Agent": UA}, timeout=45)
            if r.status_code in (429, 500, 502, 503, 504) and i < attempts - 1:
                time.sleep(2 ** i)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == attempts - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def commons_info(filename: str) -> dict | None:
    """URL + licence + author for one Commons file, or None if it is gone."""
    data = _api({
        "action": "query", "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime",
        "iiurlwidth": TARGET_W,
    })
    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        if pid == "-1" or "imageinfo" not in page:
            return None
        info = page["imageinfo"][0]
        ext = info.get("extmetadata", {})

        def field(key: str) -> str:
            raw = ext.get(key, {}).get("value", "") or ""
            # Commons returns HTML in these fields (author is often a link)
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", raw)).strip()

        return {
            "file": filename,
            "thumb": info.get("thumburl") or info["url"],
            "descriptionurl": info.get("descriptionurl", ""),
            "licence": field("LicenseShortName") or "see source",
            "licence_url": ext.get("LicenseUrl", {}).get("value", ""),
            "author": field("Artist") or "unknown",
            "terms": f"{field('UsageTerms')} {field('Permission')}".strip(),
        }
    return None


def licence_problem(info: dict) -> str | None:
    """Why this file cannot be used, or None if it is fine.

    The site carries AdSense, so it is a commercial use — a NonCommercial image
    is not licensed for it no matter how well attributed. GFDL-only is refused
    too: it obliges us to ship the full licence text alongside the work, which
    is not a thing a Hindi crop guide should be doing. Commons is full of
    CC BY / CC BY-SA / CC0 / public-domain alternatives.
    """
    haystack = f"{info['licence']} {info.get('terms', '')}".lower()
    if "-nc" in haystack or "noncommercial" in haystack or "non-commercial" in haystack:
        return f"NonCommercial ({info['licence']}) — this site runs ads"
    if "gfdl" in info["licence"].lower() and "cc" not in info["licence"].lower():
        return "GFDL-only — would require shipping the licence text"
    return None


def _flatten(im: Image.Image) -> Image.Image:
    """RGB, with any transparency composited onto white."""
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, im).convert("RGB")
    return im.convert("RGB") if im.mode != "RGB" else im


def _emit(slug: str, im: Image.Image, fit: str, source: str) -> None:
    """Write the 1200×675 hero and its 480×270 card cut."""
    im = _contain_16x9(im) if fit == "contain" else _crop_16x9(im)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{slug}.webp"
    im.save(dest, "WEBP", quality=WEBP_QUALITY, method=6)

    # /articles/ shows 79 of these in a grid whose band is ~360px wide on the
    # phones that are 98% of the traffic. Serving the 1200px hero there would be
    # ~140 KB per card for no visible gain, so each hero also gets a card cut.
    # In-body illustrations never appear on a card, so they skip it.
    kb = dest.stat().st_size // 1024
    if slug.startswith("body-"):
        print(f"  ✓ {slug}.webp  {im.width}×{im.height}  {kb} KB  ← {source}")
        return
    card = OUT_DIR / f"{slug}-card.webp"
    im.resize((CARD_W, CARD_H), Image.LANCZOS).save(
        card, "WEBP", quality=WEBP_QUALITY, method=6)
    ckb = card.stat().st_size // 1024
    print(f"  ✓ {slug}.webp  {im.width}×{im.height}  {kb} KB "
          f"(+ card {ckb} KB)  ← {source}")


def fetch_one(slug: str, filename: str, force: bool = False) -> dict | None:
    dest = OUT_DIR / f"{slug}.webp"
    if dest.is_file() and not force:
        return None
    info = commons_info(filename)
    if info is None:
        print(f"  ✗ {slug}: Commons has no File:{filename}")
        return {"__error__": filename}
    problem = licence_problem(info)
    if problem:
        print(f"  ✗ {slug}: {problem} — pick another file")
        return {"__error__": filename}
    r = requests.get(info["thumb"], headers={"User-Agent": UA}, timeout=90)
    r.raise_for_status()
    im = _flatten(Image.open(io.BytesIO(r.content)))
    if im.width < MIN_SOURCE_W:
        print(f"  ✗ {slug}: source is only {im.width}px wide — pick a bigger file")
        return {"__error__": filename}
    _emit(slug, im, "cover", filename)
    return info


def local_one(slug: str, rel: str, force: bool = False) -> bool:
    dest = OUT_DIR / f"{slug}.webp"
    src = ROOT / "frontend" / rel
    if dest.is_file() and not force:
        return True
    if not src.is_file():
        print(f"  ✗ {slug}: no such file: frontend/{rel}")
        return False
    _emit(slug, _flatten(Image.open(src)), "contain", rel)
    return True


def _crop_16x9(im: Image.Image) -> Image.Image:
    """Centre-crop to 16:9, then scale to 1200×675.

    Centre because the subject of a crop photograph is centred far more often
    than not, and a wrong crop is obvious on the card grid.
    """
    want = TARGET_W / TARGET_H
    have = im.width / im.height
    if have > want:                       # too wide — trim the sides
        w = round(im.height * want)
        left = (im.width - w) // 2
        im = im.crop((left, 0, left + w, im.height))
    elif have < want:                     # too tall — trim top and bottom
        h = round(im.width / want)
        top = (im.height - h) // 2
        im = im.crop((0, top, im.width, top + h))
    return im.resize((TARGET_W, TARGET_H), Image.LANCZOS)


def _edge_colour(im: Image.Image) -> tuple[int, int, int]:
    """The dominant colour of the image's border, to letterbox against."""
    w, h = im.size
    edge = [im.getpixel((x, 0)) for x in range(0, w, max(1, w // 60))]
    edge += [im.getpixel((x, h - 1)) for x in range(0, w, max(1, w // 60))]
    edge += [im.getpixel((0, y)) for y in range(0, h, max(1, h // 60))]
    edge += [im.getpixel((w - 1, y)) for y in range(0, h, max(1, h // 60))]
    n = len(edge)
    return tuple(sum(p[i] for p in edge) // n for i in range(3))


def _contain_16x9(im: Image.Image) -> Image.Image:
    """Fit the whole image inside 1200×675, padding to fill.

    For annotated diagrams: they carry Hindi labels right out to the edge, so
    a centre crop silently eats the text that makes them worth showing.
    """
    scale = min(TARGET_W / im.width, TARGET_H / im.height)
    fitted = im.resize((max(1, round(im.width * scale)),
                        max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (TARGET_W, TARGET_H), _edge_colour(fitted))
    canvas.paste(fitted, ((TARGET_W - fitted.width) // 2,
                          (TARGET_H - fitted.height) // 2))
    return canvas


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true", help="re-fetch images already on disk")
    p.add_argument("--verify", action="store_true",
                   help="check every source file still exists on Commons, fetch nothing")
    p.add_argument("slugs", nargs="*", help="limit to these slugs")
    args = p.parse_args()

    sys.path.insert(0, str(ROOT / "tools"))
    from article_images import IMAGES, LOCAL, BODY, body_name  # noqa: E402

    # In-body illustrations land under the same directory, keyed by a slug
    # derived from the original hotlink so the rewrite can find them.
    body = {body_name(orig): src for orig, src in BODY.items()}
    todo = {**IMAGES, **{k: v for k, v in body.items() if not v.startswith("images/")}}
    todo = {k: v for k, v in todo.items() if not args.slugs or k in args.slugs}
    todo_local = {**LOCAL, **{k: v for k, v in body.items() if v.startswith("images/")}}
    todo_local = {k: v for k, v in todo_local.items() if not args.slugs or k in args.slugs}

    if args.verify:
        missing = []
        for slug, filename in todo.items():
            info = commons_info(filename)
            if info is None:
                missing.append((slug, filename))
                print(f"  ✗ {slug}: File:{filename} is gone from Commons")
                continue
            problem = licence_problem(info)
            if problem:
                missing.append((slug, filename))
                print(f"  ✗ {slug}: {problem} ({filename})")
        print(f"\n{len(todo) - len(missing)}/{len(todo)} sources OK")
        return 1 if missing else 0

    credits = json.loads(CREDITS.read_text(encoding="utf-8")) if CREDITS.is_file() else {}
    errors = []
    for slug, filename in todo.items():
        try:
            info = fetch_one(slug, filename, force=args.force)
        except Exception as e:                      # network, decode, disk
            print(f"  ✗ {slug}: {e}")
            errors.append(slug)
            continue
        if info and "__error__" in info:
            errors.append(slug)
        elif info:
            credits[slug] = info

    # Repo-owned art: no credit entry, it is ours already.
    for slug, rel in todo_local.items():
        try:
            if not local_one(slug, rel, force=args.force):
                errors.append(slug)
        except Exception as e:
            print(f"  ✗ {slug}: {e}")
            errors.append(slug)

    CREDITS.write_text(json.dumps(credits, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
    print(f"\ncredits: {len(credits)} entries -> {CREDITS.relative_to(ROOT)}")
    if errors:
        print(f"failed: {', '.join(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
