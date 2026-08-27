#!/usr/bin/env python3
# ============================================================
# tools/fetch_rental_images.py
# Photographs for the /rental machine cards, from Wikimedia Commons.
#
# WHY A SIBLING OF fetch_article_images.py AND NOT A FLAG ON IT. That tool
# produces 1200×675 article heroes; these are 400×300 tiles that sit in a 118px
# card band and a 280px hero panel. Same source, same licence rules — so the
# Commons call and the licence gate are IMPORTED from it rather than copied —
# but a different output size, a different directory and a different credits
# file, because the two sets are added and reviewed independently.
#
# SMALL ON PURPOSE. This site blew a 5GB/month Render bandwidth cap once
# already, and 98% of its visits are phones on mobile data. A /rental equipment
# page loads one hero plus up to six sibling cards, so the whole page's imagery
# has to stay in the tens of kilobytes. 400×300 at quality 62 lands each file
# around 8–15 KB, which is ~1.4× the widest box any of them is drawn in — enough
# for a retina screen and nothing more. Do NOT raise these to "look nicer" on a
# desktop nobody is using.
#
# THE LICENCE GATE IS THE POINT, NOT THE DOWNLOAD. Every file here is
# CC BY / CC BY-SA / CC0 / public domain, and the site carries AdSense, so a
# NonCommercial image is not licensed for it however well attributed — that is
# what licence_problem() refuses. Attribution is written to CREDITS.json beside
# the images and rendered by routes/credits.py; a photo whose credit is missing
# cannot be published without it being visible there.
#
# ONE MACHINE MAY HAVE NO PHOTO. A slug absent from PICKS below keeps the emoji
# tile, and that is a deliberate outcome rather than a gap to be filled with
# something approximate. A "super seeder" page showing an ordinary seed drill
# would be teaching a farmer the wrong machine before he spends ₹2,000 an acre
# on it — see routes/rental.py::_tile, which falls back on its own.
#
#   python tools/fetch_rental_images.py            # fetch what is missing
#   python tools/fetch_rental_images.py --force    # re-fetch everything
#   python tools/fetch_rental_images.py --verify   # check the sources still exist
# ============================================================

import argparse
import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The Commons plumbing and the licence rules have ONE home.
from tools.fetch_article_images import (  # noqa: E402
    UA, commons_info, licence_problem,
)

OUT_DIR = ROOT / "frontend" / "images" / "rental"
CREDITS = OUT_DIR / "CREDITS.json"

# See the header: sized to the boxes these are actually drawn in, not to look
# good in a photo viewer.
TARGET_W = 400
TARGET_H = 300
WEBP_QUALITY = 62

# Below this an upscale to 400 is visible. Commons has alternatives; skip
# rather than ship a soft tile.
MIN_SOURCE_W = 380

# slug → Commons filename. Every one was checked to be the machine the page is
# about, not merely a plausible neighbour of it.
PICKS = {
    # ── जुताई व भूमि तैयारी ──
    "tractor":             "Mahindra Tractor, India.jpg",
    "rotavator":           "Kuhn EL201 - rotavator at Bernard Saunders WD 2008 - IMG 4072.jpg",
    "cultivator":          "Perfecta II field cultivator 1.jpg",
    "disc-harrow":         "Disc harrow by Case IH.JPG",
    "power-tiller":        "Mini Tiller.png",
    "laser-land-leveller": "Agriculture Land leveler 02.jpg",
    # ── बुवाई व रोपाई ──
    "seed-drill":          "Grain Seed Drill Machine 01.jpg",
    "happy-seeder":        "National Agro Happy Seeder.jpg",
    "zero-till-drill":     "No-till Planting (8120028117).jpg",
    "paddy-transplanter":  "Rice-planting-machine,katori-city,japan.JPG",
    # super-seeder: no accurate photo on Commons — keeps its emoji, see header.
    # ── सिंचाई ──
    "pump-set":            "20220709 Irrigation pump.jpg",
    "sprinkler-set":       "NRBC distributary 10 sprinkler irrigation fields Raichur Karnataka India.jpg",
    "rain-gun":            "On sprinkler dolly mounted rain gun.jpg",
    # ── छिड़काव व फसल सुरक्षा ──
    "power-sprayer":       "Sweet potato farmers in Peru with pesticide sprayers.jpg",
    "boom-sprayer":        "Tractor and boom sprayer degania spayer archive-002.jpg",
    "drone-sprayer":       "Agricultural drone spraying on paddy field.jpg",
    # ── कटाई, मड़ाई व चारा ──
    "combine-harvester":   "A combine harvester at work in a field of wheat - geograph.org.uk - 6246353.jpg",
    "thresher":            "Paddy thresher.jpg",
    "reaper-binder":       "Harvesting with reaper and binder - 1 - geograph.org.uk - 2568380.jpg",
    "straw-baler":         "John Deere 338 square baler 1.jpg",
    "chaff-cutter":        "Fodder chopper.jpg",
    # ── ढुलाई व मिट्टी का काम ──
    "tractor-trolley":     "A tractor trailer - geograph.org.uk - 379906.jpg",
    "jcb":                 "JCB 3CX ECO backhoe loader at VDNKh, Moscow.jpg",
}


def _load_credits() -> dict:
    if CREDITS.exists():
        try:
            return json.loads(CREDITS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_credits(rows: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CREDITS.write_text(
        json.dumps(dict(sorted(rows.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def _cover(im: Image.Image) -> Image.Image:
    """Fill 400×300, cropping the long side.

    `cover` rather than `contain` because both boxes these land in are fixed
    ratio: letterboxing would leave bands of dead colour inside an already
    small card. The crop is centred, which is where a photographer puts a
    machine they are photographing.
    """
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.split()[-1])
        im = flat
    else:
        im = im.convert("RGB")
    scale = max(TARGET_W / im.width, TARGET_H / im.height)
    im = im.resize((max(1, round(im.width * scale)),
                    max(1, round(im.height * scale))), Image.LANCZOS)
    left = (im.width - TARGET_W) // 2
    top = (im.height - TARGET_H) // 2
    return im.crop((left, top, left + TARGET_W, top + TARGET_H))


def fetch_one(slug: str, filename: str, force: bool) -> dict | None:
    dest = OUT_DIR / f"{slug}.webp"
    if dest.exists() and not force:
        print(f"  · {slug}.webp already here")
        return None

    info = commons_info(filename)
    if not info:
        print(f"  ✗ {slug}: Commons has no File:{filename}")
        return None
    problem = licence_problem(info)
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
    print(f"  ✓ {slug}.webp  {TARGET_W}×{TARGET_H}  {kb:.1f} KB  ← {info['author'][:34]}")
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-fetch even if present")
    ap.add_argument("--verify", action="store_true",
                    help="check every source still exists and is still usable")
    ap.add_argument("--only", default="", help="one slug")
    args = ap.parse_args()

    picks = PICKS
    if args.only:
        if args.only not in PICKS:
            print(f"unknown slug {args.only!r}")
            return 2
        picks = {args.only: PICKS[args.only]}

    if args.verify:
        bad = 0
        for slug, filename in picks.items():
            info = commons_info(filename)
            if not info:
                print(f"  ✗ {slug}: GONE — File:{filename}")
                bad += 1
                continue
            problem = licence_problem(info)
            if problem:
                print(f"  ✗ {slug}: {problem}")
                bad += 1
            else:
                print(f"  ✓ {slug}: {info['licence']}")
        print(f"\n{len(picks) - bad}/{len(picks)} usable")
        return 1 if bad else 0

    rows = _load_credits()
    got = 0
    for slug, filename in picks.items():
        try:
            info = fetch_one(slug, filename, args.force)
        except Exception as e:
            print(f"  ✗ {slug}: {e}")
            continue
        if info:
            rows[slug] = {k: info[k] for k in
                          ("author", "descriptionurl", "file", "licence",
                           "licence_url", "thumb") if k in info}
            got += 1
    if got:
        _save_credits(rows)
    total = sum(f.stat().st_size for f in OUT_DIR.glob("*.webp")) / 1024 if OUT_DIR.exists() else 0
    print(f"\n{got} fetched · {len(list(OUT_DIR.glob('*.webp')))} files · {total:.0f} KB total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
