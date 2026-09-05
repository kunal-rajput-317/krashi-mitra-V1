# ============================================================
# tests/test_no_hotlinked_images.py
#
# Nothing this site serves may load an image from someone else's server.
#
# This is not a style rule. On 2026-09-04 an audit found every one of these,
# all of them live:
#
#   • Two published /krashi_news posts hotlinked upload.wikimedia.org, and one
#     illustrated a Tamil Nadu paddy-compensation story with a portrait of a
#     named, living public figure who had nothing to do with it.
#   • ~210 crop photographs behind the mandi grid and every og:image were
#     built into Commons thumb URLs at request time with no credit anywhere —
#     and ELEVEN of them were NonCommercial or GFDL-only, which an
#     AdSense-carrying site may not use at any level of attribution.
#   • The WhatsApp mark was pulled through Wikimedia in six places.
#   • Three /rental cards fell back to hotlinked photos of branded vehicles.
#
# The failure mode is quiet: the page looks right, so nothing draws attention
# to it until a licence complaint, a takedown, or the file being renamed on
# Commons turns it into a broken image on the busiest pages on the site.
#
# The fix in every case was the same and is already in place — fetch it once,
# licence-check it, self-host it, credit the author on /articles/credits
# (tools/fetch_crop_images.py, tools/fetch_article_images.py,
# tools/fetch_rental_images.py). This test is what stops the next paste from
# undoing it.
#
# If this fails: do NOT add the host to ALLOWED. Run the matching fetch tool,
# or drop the image. An approximate photo is worse than no photo — see the
# header of tools/fetch_rental_images.py.
# ============================================================

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Directories whose served content must never reference a third-party image.
SCAN_DIRS = [
    ROOT / "frontend",
    ROOT / "backend",
    ROOT / "admin",
]

SCAN_SUFFIXES = {".html", ".js", ".py", ".json"}

# Files that legitimately name these hosts without serving from them:
# the fetch tools DOWNLOAD from Commons (that is the fix, not the problem),
# the credits page LINKS to the licence and the file description page, and
# CREDITS.json records the source URL of the original as provenance.
EXEMPT_PARTS = {
    ROOT / "tools",
    ROOT / "tests",
    ROOT / "node_modules",
    ROOT / "docs",
    ROOT / "scratch",
}
EXEMPT_FILES = {
    ROOT / "backend" / "routes" / "credits.py",       # links to commons.wikimedia.org
}
EXEMPT_NAMES = {"CREDITS.json"}                        # provenance records

# Image-serving hosts we have actually been caught hotlinking.
BANNED = re.compile(
    r"https?://(?:upload\.wikimedia\.org|commons\.wikimedia\.org/wiki/Special:FilePath)"
    r"|//upload\.wikimedia\.org",
    re.I,
)


def _files():
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if f.name in EXEMPT_NAMES or f in EXEMPT_FILES:
                continue
            if any(part in f.parents for part in EXEMPT_PARTS):
                continue
            yield f


def test_no_hotlinked_third_party_images():
    """No served file may build or embed a Wikimedia image URL."""
    offenders = []
    for f in _files():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if BANNED.search(line):
                rel = f.relative_to(ROOT)
                offenders.append(f"{rel}:{i}: {line.strip()[:110]}")

    assert not offenders, (
        "These files hotlink a third-party image host. Self-host it instead "
        "(tools/fetch_crop_images.py, fetch_article_images.py, "
        "fetch_rental_images.py) so the author is credited on /articles/credits:"
        "\n  " + "\n  ".join(offenders)
    )


def test_stored_post_images_are_same_origin():
    """No image path saved in a data file may be an absolute URL.

    news_funnel.json is written by the auto-pilot and by the admin image
    updater, which accepts a pasted link — the exact route by which a
    hotlinked portrait of a named person reached the live site.
    """
    bad = []
    for rel in ("backend/data/news_funnel.json", "backend/data/rental_equipment.json"):
        path = ROOT / rel
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))

        def walk(node, trail=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in ("image", "img", "wiki_img", "media_url") and isinstance(v, str) \
                            and v.startswith(("http://", "https://", "//")):
                        bad.append(f"{rel}{trail}.{k} = {v[:80]}")
                    else:
                        walk(v, f"{trail}.{k}")
            elif isinstance(node, list):
                for idx, v in enumerate(node):
                    walk(v, f"{trail}[{idx}]")

        walk(data)

    assert not bad, (
        "Stored image fields must be same-origin paths (/images/...):\n  "
        + "\n  ".join(bad)
    )


# Served images whose source we could not establish. They are NOT Commons
# downloads recorded by any fetch tool, and they are not in article_images.LOCAL
# (the site's own artwork), so either they are the owner's own photographs — in
# which case they need no credit and belong in LOCAL — or they were saved from
# somewhere and need one. Listed here so the check can run over everything else
# instead of being switched off, and so they stay visible until resolved.
# Resolve, do not extend: a new name here means a new uncredited photograph.
PROVENANCE_UNCONFIRMED = {
    "motha-ghaas-01",   # frontend/articles/motha-ghaas-UP.html
    "motha-ghaas-02",   # frontend/articles/motha-ghaas-UP.html
    "potato",           # frontend/index.html
}


@pytest.mark.parametrize("credits_rel", [
    "frontend/images/crops/CREDITS.json",
    "frontend/images/articles/CREDITS.json",
    "frontend/images/rental/CREDITS.json",
])
def test_every_self_hosted_image_has_attribution(credits_rel):
    """Every .webp we serve from an image directory must name its author.

    CC BY and CC BY-SA are both conditional on attribution, so a served file
    with no row in CREDITS.json is a photograph published without the term its
    licence depends on.
    """
    credits_path = ROOT / credits_rel
    img_dir = credits_path.parent
    if not img_dir.is_dir():
        pytest.skip(f"{credits_rel} not present")
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.is_file() else {}

    # Images the site already owned before any Commons fetch. Declared in the
    # manifest rather than guessed, so "ours" is a statement someone made.
    local = set()
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from article_images import LOCAL, BODY, body_name  # noqa: E402
        local = set(LOCAL)
        local |= {body_name(k) for k, v in BODY.items() if str(v).startswith("images/")}
    except Exception:
        pass

    missing = []
    for webp in sorted(img_dir.glob("*.webp")):
        name = webp.stem
        if name in credits or name in local or name in PROVENANCE_UNCONFIRMED:
            continue
        # A "<slug>-card.webp" is the card cut of a hero already credited as
        # "<slug>". Strip the suffix ONLY when that actually resolves — real
        # slugs end in "-card" too (kisan-credit-card, mitti-jaanch-soil-
        # health-card), and a blind strip drops exactly the photographs it
        # must not. See the same warning in routes/credits.py.
        if name.endswith("-card") and (name[:-5] in credits or name[:-5] in local):
            continue
        missing.append(name)

    listed = "".join(f"\n  {m}" for m in missing[:25])
    assert not missing, (
        f"{credits_rel}: served images with no author credit "
        "(run the matching fetch tool, or declare them in "
        f"article_images.LOCAL if they are ours):{listed}"
    )
