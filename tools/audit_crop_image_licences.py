# ============================================================
# KrashiMitra — licence audit for the hotlinked crop photos
#
# backend/routes/share.py carries ~210 Wikimedia Commons filenames used for
# two live surfaces: the og:image on every share card, and (via the same
# filenames in frontend/index.html and meri_fasal.html) the mandi grid
# thumbnails. All of them are hotlinked straight from upload.wikimedia.org.
#
# tools/fetch_article_images.py already established the compliant pattern for
# ARTICLE heroes — fetch once, self-host, record author + licence, render the
# credit on /articles/credits. These 210 never went through it, so they carry
# three problems the article images do not:
#
#   1. No attribution at all. CC BY / CC BY-SA require visible credit.
#   2. NonCommercial images would be flat-out unlicensed here — this site
#      runs AdSense, which makes it a commercial use. licence_problem() in
#      the fetch tool exists precisely for this, and none of these were
#      ever checked by it.
#   3. Hotlinking: Commons bandwidth, Commons rate limits, and a dead image
#      the moment a file is renamed (six article hotlinks had already rotted
#      when the article tool was written).
#
# This script only READS. It resolves every filename against the Commons API
# and reports which are unusable, which need attribution, and which are
# already gone — so the scale of the fix is known before anything is
# downloaded or rewritten.
#
#   python tools/audit_crop_image_licences.py
#   python tools/audit_crop_image_licences.py --json scratch/crop_licences.json
# ============================================================

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.fetch_article_images import commons_info, licence_problem  # noqa: E402


def _filenames() -> list[str]:
    """Every distinct Commons filename share.py can emit."""
    from backend.routes import share
    seen, out = set(), []
    for _keys, fname, _hash in share._TILES:
        if fname not in seen:
            seen.add(fname)
            out.append(fname)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="PATH", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = _filenames()
    if args.limit:
        files = files[:args.limit]
    print(f"auditing {len(files)} Commons files referenced by share.py\n")

    rows, blocked, missing = [], [], []
    lic_count = Counter()

    for i, fname in enumerate(files, 1):
        try:
            info = commons_info(fname)
        except Exception as e:
            print(f"  [{i:>3}/{len(files)}] ERROR  {fname}: {e}")
            missing.append({"file": fname, "why": f"api error: {e}"})
            continue

        if not info:
            print(f"  [{i:>3}/{len(files)}] GONE   {fname}")
            missing.append({"file": fname, "why": "not found on Commons"})
            continue

        problem = licence_problem(info)
        lic_count[info["licence"]] += 1
        row = {**info, "problem": problem}
        rows.append(row)
        if problem:
            blocked.append(row)
            print(f"  [{i:>3}/{len(files)}] BLOCK  {fname} — {problem}")

        # Commons asks for courteous rates; the article tool hits 429s without this.
        time.sleep(0.12)

    print("\n" + "=" * 62)
    print(f"resolved OK          : {len(rows)}")
    print(f"missing / renamed    : {len(missing)}")
    print(f"licence-BLOCKED      : {len(blocked)}  (cannot be used on an ad-supported site)")
    print("\nlicence breakdown:")
    for lic, n in lic_count.most_common():
        print(f"  {n:>4}  {lic}")

    if missing:
        print("\nmissing files (these are already broken images on the live site):")
        for m in missing:
            print(f"  {m['file']} — {m['why']}")

    if blocked:
        print("\nBLOCKED — must be replaced, not merely self-hosted:")
        for b in blocked:
            print(f"  {b['file']}\n      {b['problem']}\n      {b['descriptionurl']}")

    if args.json:
        out = ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"ok": rows, "blocked": blocked, "missing": missing},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
