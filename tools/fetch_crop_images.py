#!/usr/bin/env python3
# ============================================================
# tools/fetch_crop_images.py
# Crop photographs for the mandi grid and the og:image on share cards.
#
# WHY THIS EXISTS. backend/routes/share.py holds ~210 Wikimedia Commons
# filenames plus their CDN shard hashes, and built upload.wikimedia.org URLs
# at request time. The same filenames drive the homepage mandi thumbnails
# (frontend/index.html) and the crop chips on meri_fasal.html. None of it went
# through the licence gate the article and rental images go through, so it
# carried three faults the other two sets do not:
#
#   • No attribution anywhere. CC BY and CC BY-SA both require visible credit.
#   • ELEVEN of the 210 are not licensed for this site at all — five are
#     NonCommercial (GFDL 1.2) and six are GFDL-only, and KrashiMitra carries
#     AdSense, which makes every page a commercial use. Attribution cannot fix
#     those; only replacement can. See REPLACEMENTS below.
#   • Hotlinking: Commons bandwidth and rate limits on every card render, and
#     a dead image the day a file is renamed.
#
# The Commons call and the licence gate are IMPORTED from
# fetch_article_images.py rather than copied, so there is one definition of
# "which licences may we use" for the whole site.
#
#   python tools/fetch_crop_images.py             # fetch what is missing
#   python tools/fetch_crop_images.py --force     # re-fetch everything
#   python tools/fetch_crop_images.py --verify    # licence check only, no writes
#
# ONE SIZE, ON PURPOSE. 800×450 at quality 72 lands each file near 30-50 KB.
# It is the smallest thing that still satisfies both consumers: the mandi card
# draws at ~190px (so 800 covers 2x DPR with room to spare) and og:image wants
# at least 600×315 for a large share card. Two size variants were considered
# and rejected — 420 files to save a few KB on a grid that lazy-loads anyway.
# This site blew a 5 GB/month bandwidth cap once; do not raise these.
#
# Attribution lands in frontend/images/crops/CREDITS.json and is rendered by
# routes/credits.py on /articles/credits, the same page the article and rental
# images already credit through.
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
sys.path.insert(0, str(ROOT))

from tools.fetch_article_images import (  # noqa: E402
    UA, commons_info, licence_problem, _flatten,
)

OUT_DIR = ROOT / "frontend" / "images" / "crops"
CREDITS = OUT_DIR / "CREDITS.json"

TARGET_W = 800
TARGET_H = 450
WEBP_QUALITY = 72
MIN_SOURCE_W = 400        # below this the upscale to 800 is visible

# ── Substitutions ───────────────────────────────────────────────────────
# Eleven because the licence gate refuses them, two because the Commons
# original is too small to publish.
# Each of these is currently live on the site under a licence that does not
# permit commercial use, or one whose terms we cannot meet. They are swapped
# for a freely-licensed photograph of the SAME subject; the mapping is
# explicit rather than an automated Commons search so that the substitute is
# actually of the right crop, which a search cannot guarantee. Verified with
# `--verify` — every replacement resolves and passes licence_problem().
REPLACEMENTS = {
    # original (unusable licence)              → free-licensed stand-in
    "Bright red tomato and cross section02.jpg": "Tomato je.jpg",
    "Mint_leaves.jpg":                           "Corn Mint (Mentha arvensis).jpg",
    "Pomegranate.jpg":                           "Pomegranate fruit - whole and piece with arils.jpg",
    "Grapes.jpg":                                "Bunch of grapes amidst vine leaves, Ponte de Sor (approx. GPS location) julesvernex2.jpg",
    "Apricot and cross section.jpg":             "Apricots.jpg",
    "Sugar apple on tree.jpg":                   "Sitaphal (Custard apple), India.jpg",
    "Chayote BNC.jpg":                           "Sechium edule dsc07767.jpg",
    "Red Rajma BNC.jpg":                         "Kidney beans.jpg",
    "Heaps of beans.jpg":                        "Phaseolus vulgaris seeds.jpg",
    "Sunflower sky backdrop.jpg":                "Sunflowers helianthus annuus.jpg",
    "Fodder factory02.jpg":                      "Harvest Straw Bales in Schleswig-Holstein.jpg",

    # Not a licence problem — the Commons originals are 350px and 388px, below
    # MIN_SOURCE_W, so they failed the first run outright. Chickpea matters:
    # चना is a major crop and is referenced by krashi_bajar and meri_fasal too.
    "Chickpea.jpg":                              "Cicer arietinum - Kolkata 2003-10-31 00533.JPG",
    "Tinda.jpg":                                 "Young round gourd fruits with yellow flowers in home garden.jpg",
}


# Commons filenames that are not in Latin script. The ASCII slug rule below
# reduces each of these to an empty string, and four different crops
# (sapota, pineapple, broomstick, tulip) therefore collapsed onto ONE file
# that each overwrote in turn. Named explicitly rather than hashed, because
# the slug has to be reproducible by hand from share.py's table and a hash
# is not readable in a URL.
_SLUG_ALIASES = {
    "സപ്പോട്ട.jpg": "sapota",
    "കൈതച്ചക്ക.jpg": "pineapple",
    "अम्रिसो.jpg": "broomstick-grass",
    "צבעונים.JPG": "tulip",
}


def crop_slug(filename: str) -> str:
    """'Rice_grains_(IRRI).jpg' → 'rice-grains-irri'. Derived from the Commons
    filename, never hand-assigned, so the name on disk and the name in
    share.py's table cannot drift apart.

    Note that Commons treats a space and an underscore in a title as the same
    character, so 'Luffa acutangula.jpg' and 'Luffa_acutangula.jpg' are one
    file and correctly share one slug."""
    if filename in _SLUG_ALIASES:
        return _SLUG_ALIASES[filename]
    stem = filename.rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def _filenames() -> list[str]:
    from backend.routes import share
    seen, out = set(), []
    for _keys, fname, _hash in share._TILES:
        if fname not in seen:
            seen.add(fname)
            out.append(fname)
    return out


def _cover(im: Image.Image) -> Image.Image:
    """Fill 800×450, centre-cropping whatever overflows."""
    im = _flatten(im)
    scale = max(TARGET_W / im.width, TARGET_H / im.height)
    im = im.resize((max(TARGET_W, int(im.width * scale + 0.5)),
                    max(TARGET_H, int(im.height * scale + 0.5))), Image.LANCZOS)
    left = (im.width - TARGET_W) // 2
    top = (im.height - TARGET_H) // 2
    return im.crop((left, top, left + TARGET_W, top + TARGET_H))


def _load_credits() -> dict:
    if CREDITS.is_file():
        try:
            return json.loads(CREDITS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_credits(rows: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CREDITS.write_text(json.dumps(rows, ensure_ascii=False, indent=2,
                                  sort_keys=True), encoding="utf-8")


def resolve(filename: str) -> tuple[str, dict | None, str | None]:
    """(effective filename, info, problem). Applies REPLACEMENTS first."""
    effective = REPLACEMENTS.get(filename, filename)
    info = commons_info(effective)
    if not info:
        return effective, None, "not found on Commons"
    return effective, info, licence_problem(info)


def fetch_one(filename: str, force: bool) -> dict | None:
    slug = crop_slug(filename)          # slug follows the ORIGINAL name, so
    dest = OUT_DIR / f"{slug}.webp"     # share.py's table needs no rewrite
    if dest.is_file() and not force:
        return None

    effective, info, problem = resolve(filename)
    if not info:
        print(f"  ✗ {slug}: {effective} not found on Commons")
        return None
    if problem:
        print(f"  ✗ {slug}: {problem}")
        return None

    r = requests.get(info["thumb"], headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content))
    if im.width < MIN_SOURCE_W:
        print(f"  ✗ {slug}: source only {im.width}px wide")
        return None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _cover(im).save(dest, "WEBP", quality=WEBP_QUALITY, method=6)
    kb = dest.stat().st_size / 1024
    swapped = " (replaced)" if effective != filename else ""
    print(f"  ✓ {slug}.webp  {kb:>5.1f} KB  {info['licence']:<16}"
          f" ← {info['author'][:30]}{swapped}")
    return {**info, "original": filename, "slug": slug}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="licence-check every file, write nothing")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = _filenames()
    if args.limit:
        files = files[:args.limit]

    if args.verify:
        bad = 0
        for i, f in enumerate(files, 1):
            effective, info, problem = resolve(f)
            if not info or problem:
                bad += 1
                print(f"  ✗ {f} → {effective}: {problem or 'not found'}")
            time.sleep(0.1)
        print(f"\n{len(files) - bad}/{len(files)} usable")
        return 1 if bad else 0

    credits = _load_credits()
    got = 0
    for i, f in enumerate(files, 1):
        try:
            row = fetch_one(f, args.force)
        except Exception as e:
            print(f"  ✗ {crop_slug(f)}: {e}")
            continue
        if row:
            credits[row["slug"]] = row
            got += 1
        time.sleep(0.1)

    if got:
        _save_credits(credits)
    total = sum(x.stat().st_size for x in OUT_DIR.glob("*.webp")) / 1024 if OUT_DIR.exists() else 0
    print(f"\nfetched {got}; {len(list(OUT_DIR.glob('*.webp')))} files, {total/1024:.1f} MB total")
    print(f"credits → {CREDITS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
