"""Shrink the site's heavy images in place, keeping every URL unchanged.

Why: Render bills every byte it sends against a 5 GB/month cap, and Cloudflare's
free plan evicts rarely-requested files quickly, so a 400 KB article hero is
re-fetched from Render again and again. On 25 Sep 2026, 145 referenced images
were over 150 KB (35 MB in total) — most of them 1200 px article heroes from
fetch_article_images.py at WebP q82, and the state maps' PNG "HD download"
copies, which are flat-colour graphics stored as 24-bit PNG.

What it does (idempotent — a second run changes nothing):
  * .webp / .jpg / .jpeg over the budget: scale down to at most MAX_W wide and
    re-encode at QUALITY. On the phones that are 98% of traffic the display box
    is ~390 CSS px, so 960 px still covers a 2.5x screen.
  * .png over the budget with few colours (maps, logos, cards): quantise to a
    256-colour palette without dithering — visually identical for flat art.
    Photographic PNGs are left alone; quantising them would band.
  * A file is only replaced if the result is at least MIN_SAVING smaller.

Usage:  python tools/shrink_images.py            # shrink
        python tools/shrink_images.py --dry-run  # report only
"""

import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "frontend" / "images", ROOT / "frontend" / "assets"]
BUDGET = 150_000
MAX_W = 960
QUALITY = 75
MIN_SAVING = 0.15
FLAT_COLOURS = 20_000        # below this many distinct colours a PNG is "flat art"


def shrink_photo(path: Path, im: Image.Image) -> bytes:
    fmt = "WEBP" if path.suffix.lower() == ".webp" else "JPEG"
    if im.mode not in ("RGB", "L") and fmt == "JPEG":
        im = im.convert("RGB")
    elif im.mode == "P":
        im = im.convert("RGBA")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    if fmt == "WEBP":
        im.save(buf, "WEBP", quality=QUALITY, method=6)
    else:
        im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def shrink_png(im: Image.Image) -> bytes | None:
    rgba = im.convert("RGBA")
    colours = rgba.getcolors(FLAT_COLOURS)
    if colours is None:            # more than FLAT_COLOURS — photographic, leave it
        return None
    has_alpha = any(c[1][3] < 255 for c in colours)
    q = (rgba.quantize(256, method=Image.FASTOCTREE, dither=Image.NONE) if has_alpha
         else rgba.convert("RGB").quantize(256, method=Image.MEDIANCUT, dither=Image.NONE))
    buf = io.BytesIO()
    q.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main(dry: bool) -> None:
    before = after = n = 0
    for d in DIRS:
        for path in sorted(d.rglob("*")):
            ext = path.suffix.lower()
            if ext not in (".webp", ".jpg", ".jpeg", ".png") or not path.is_file():
                continue
            size = path.stat().st_size
            if size <= BUDGET:
                continue
            try:
                with Image.open(path) as im:
                    im.load()
                    if getattr(im, "is_animated", False):
                        continue
                    data = shrink_png(im) if ext == ".png" else shrink_photo(path, im)
            except Exception as e:
                print(f"  ! {path.relative_to(ROOT)}: {e}")
                continue
            if not data or len(data) > size * (1 - MIN_SAVING):
                continue
            n += 1
            before += size
            after += len(data)
            print(f"  {size // 1024:>4} KB -> {len(data) // 1024:>4} KB  {path.relative_to(ROOT)}")
            if not dry:
                path.write_bytes(data)
    print(f"\n{n} files: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB"
          f"{' (dry run)' if dry else ''}")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
