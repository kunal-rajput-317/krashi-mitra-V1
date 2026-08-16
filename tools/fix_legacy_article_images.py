# ============================================================
# KrashiMitra — bring the hand-written articles up to the hero-image contract
#
# The 43 builder-generated articles get their hero from `hero_image` in their
# content module. The 36 older hand-written pages predate the builder and were
# each in one of three broken states:
#
#   • no picture at all (10 of them) — the /articles/ card fell back to an emoji
#   • a picture hotlinked from commons.wikimedia.org — six of those files had
#     been renamed or deleted upstream and were rendering as broken-image icons
#   • og:image left at the generic site banner, so the SERP and WhatsApp preview
#     showed the KrashiMitra logo rather than the crop
#
# This script fixes all three from tools/article_images.py, which is also what
# fetch_article_images.py fetches from — so the page, the card and og:image can
# only ever point at the same file.
#
#   python tools/fix_legacy_article_images.py            # apply
#   python tools/fix_legacy_article_images.py --dry-run  # report only
#
# It is idempotent: running it twice changes nothing the second time. Once an
# article is migrated to a content module this stops touching it.
# ============================================================

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
ARTICLES = FRONTEND / "articles"
SITE = "https://krashimitra.in"

sys.path.insert(0, str(ROOT / "tools"))
from article_images import IMAGES, LOCAL, BODY, body_name  # noqa: E402

# Four articles still have mixed-case filenames (soyabean-MP-guide, MOP-guide,
# DAP-guide-up, PM-kisan-samman-nidhi) while their canonical URL and card href
# are lowercase. Index by lowercase but keep the real key, because the file on
# disk carries the mixed case and Netlify's filesystem is case-sensitive even
# though the Windows one this is authored on is not.
HEROES = {k.lower(): k for k in (*IMAGES, *LOCAL)}

# Article text for the pages that had no figure at all. Everything else keeps
# the alt and caption it already had.
CAPTIONS = {
    "aalu-pichheti-jhulsa": ("आलू की पत्ती पर पछेती झुलसा",
        "आलू की पत्ती पर पछेती झुलसा (Late Blight) — किनारों से शुरू होकर फैलने वाले भूरे-काले धब्बे।"),
    "dhan-jhonka-rog": ("धान के खेत में झोंका रोग",
        "धान के खेत में झोंका (ब्लास्ट) रोग का प्रकोप — सूखे, भूरे धब्बों वाले हिस्से साफ दिखते हैं।"),
    "gehun-ratua-rog": ("गेहूं की पत्ती पर रतुआ (गेरुई)",
        "गेहूं की पत्ती पर भूरा रतुआ (Puccinia triticina) — छूने पर हाथ में जंग जैसा पाउडर लगता है।"),
    "gehuu-price-analytic-up": ("गेहूं की कटाई",
        "गेहूं की कटाई — मंडी भाव कटाई के तुरंत बाद सबसे नीचे रहता है।"),
    "karnataka-monsoon": ("मानसून के बादल",
        "मानसून के बादल — कर्नाटक की खरीफ बुवाई पूरी तरह इसी के समय पर टिकी है।"),
    "keet-niyantran": ("नीम का तेल — जैविक कीटनाशक",
        "नीम का तेल — सबसे सस्ता और सबसे भरोसेमंद देसी कीट नियंत्रण।"),
    "land-price-up": ("उत्तर प्रदेश में कृषि भूमि",
        "वृंदावन, उत्तर प्रदेश में बोरवेल और पंप सेट वाला खेत — सिंचाई की सुविधा ज़मीन का दाम सबसे ज़्यादा बढ़ाती है।"),
    "moongfali-guide-rajisthan": ("मूंगफली का पौधा और फलियाँ",
        "मूंगफली का पौधा — फलियाँ ज़मीन के नीचे बनती हैं, इसलिए मिट्टी का भुरभुरा होना ज़रूरी है।"),
    "sarso-guide-up": ("सरसों का खिला हुआ खेत",
        "फूल की अवस्था में सरसों का खेत — यही वह समय है जब माहू का हमला सबसे ज़्यादा होता है।"),
    "tomato-leaf-curl": ("टमाटर का पौधा",
        "टमाटर का पौधा — पत्ती मरोड़ रोग सफेद मक्खी के ज़रिए एक पौधे से दूसरे तक पहुँचता है।"),
}

FIGURE = """
  <!-- FEATURED IMAGE -->
  <figure class="featured-image">
    <img src="../{path}" alt="{alt}" width="1200" height="675" loading="eager" fetchpriority="high" decoding="async" />
    <figcaption>{caption}</figcaption>
  </figure>
"""

# The .featured-image rules, for the two pages that render a figure without
# ever having had the CSS for it.
FIGURE_CSS = """
    /* ── FEATURED IMAGE ── */
    .featured-image {
      width: 100%; border-radius: 14px; overflow: hidden;
      box-shadow: 0 6px 24px rgba(0,0,0,0.12);
      background: #c8e6c9; margin: 0 0 28px;
    }
    .featured-image img { width: 100%; height: auto; display: block; }
    .featured-image figcaption {
      padding: 9px 16px; font-family: 'Poppins', sans-serif;
      font-size: 0.75rem; color: #5b6b5e; background: #f1f8e9; text-align: center;
    }
"""


def hero_for(stem: str) -> str | None:
    """frontend-relative path of this article's hero, if we fetched one."""
    key = HEROES.get(stem.lower())
    if key and (FRONTEND / f"images/articles/{key}.webp").is_file():
        return f"images/articles/{key}.webp"
    return None


def fix(path: Path, dry: bool) -> list[str]:
    text = original = path.read_text(encoding="utf-8")
    hero = hero_for(path.stem)
    notes: list[str] = []
    if not hero:
        return notes

    # 1. Every Commons hotlink becomes its own self-hosted copy — one local file
    #    per original, so a page that showed five different photographs still
    #    shows five. Six of the originals were 404 upstream; the rest rate-limit
    #    when 25 of them load at once.
    def swap(m: re.Match) -> str:
        original_name = unquote(m.group(1))
        local = f"images/articles/{body_name(original_name)}.webp"
        if original_name not in BODY or not (FRONTEND / local).is_file():
            unknown.append(original_name)
            return m.group(0)
        return f'src="../{local}"'

    unknown: list[str] = []
    text, n_hot = re.subn(
        r'src="https?://[^"]*Special:FilePath/([^"?]+)[^"]*"', swap, text)
    if n_hot - len(unknown):
        notes.append(f"self-hosted {n_hot - len(unknown)} Commons image(s)")
    for u in unknown:
        notes.append(f"UNMAPPED Commons file, left as-is: {u}")

    # 2. og:image / twitter:image / schema image → this article's own picture.
    absolute = f"{SITE}/{hero}"
    changed_og = False
    for attr, tag in (("property", "og:image"), ("name", "twitter:image")):
        pat = rf'(<meta {attr}="{re.escape(tag)}" content=")[^"]*(")'
        new, n = re.subn(pat, rf'\g<1>{absolute}\g<2>', text)
        if n and new != text:
            text, changed_og = new, True
    banner = f'"image": "{SITE}/images/og-banner.jpg"'
    if banner in text:
        text = text.replace(banner, f'"image": "{absolute}"')
        changed_og = True
    if changed_og:
        notes.append("og:image → own hero")

    # 3. A page that already has a figure gets its image normalised to the
    #    manifest hero. For most that is the same photograph at 1200×675; for
    #    potato_guide_up and PM-kisan-samman-nidhi it is a real replacement,
    #    because what they were showing was a baked-in transparency
    #    checkerboard and a mock Government of India cheque respectively.
    fig = re.search(r'<figure class="featured-image">.*?</figure>', text, re.S)
    if fig and f'src="../{hero}"' not in fig.group(0):
        fixed = re.sub(r'(<img\b[^>]*\bsrc=")[^"]*(")', rf'\g<1>../{hero}\g<2>',
                       fig.group(0), count=1)
        if fixed != fig.group(0):
            text = text.replace(fig.group(0), fixed)
            notes.append("hero figure → normalised image")

    # 4. A page with no figure at all gets one, inside .article-wrapper where
    #    every other hand-written article already puts it.
    if 'class="featured-image"' not in text:
        alt, caption = CAPTIONS.get(path.stem, (path.stem, ""))
        anchor = '<div class="article-wrapper">'
        if anchor not in text:
            notes.append("SKIPPED figure: no .article-wrapper")
        else:
            i = text.index(anchor) + len(anchor)
            text = text[:i] + FIGURE.format(path=hero, alt=alt, caption=caption) + text[i:]
            notes.append("inserted hero figure")
            if ".featured-image {" not in text:
                j = text.index("  </style>")
                text = text[:j] + FIGURE_CSS + text[j:]
                notes.append("added .featured-image CSS")

    if text != original and not dry:
        path.write_text(text, encoding="utf-8")
    return notes


CARD_IMG = ('<img src="../{card}" alt="{alt}" loading="lazy" decoding="async" '
            "onerror=\"this.closest('.article-media').classList.add('noimg');"
            'this.remove()">')


def fix_index_cards(dry: bool) -> list[str]:
    """Point every hand-written article's card at its own self-hosted cut.

    The builder does this for the generated articles. These 36 cards were
    written by hand and still carried the Commons hotlink — 25 requests to
    commons.wikimedia.org on one page load, which is how a 429 turns a card
    grid into a grid of emoji.
    """
    index = ARTICLES / "index.html"
    doc = original = index.read_text(encoding="utf-8")
    notes = []

    for m in list(re.finditer(r'<a class="article-card" href="([^"]+)".*?</a>',
                              doc, re.S)):
        slug = m.group(1).strip("/").split("/")[-1].removesuffix(".html")
        hero = hero_for(slug)
        if not hero:
            continue
        card = hero.replace(".webp", "-card.webp")
        if not (FRONTEND / card).is_file():
            card = hero
        block = m.group(0)
        if f'src="../{card}"' in block:
            continue
        title = re.search(r'<div class="article-title"[^>]*>([^<]*)', block)
        alt = (title.group(1).strip() if title else slug).replace('"', "&quot;")
        img = CARD_IMG.format(card=card, alt=alt)
        if "<img" in block:
            new = re.sub(r'<img\b[^>]*>', img, block, count=1)
        else:   # emoji-only band — put the image in front of the emoji
            new = block.replace('<span class="article-media-emoji">',
                                img + '\n        <span class="article-media-emoji">')
            new = new.replace('class="article-media noimg"', 'class="article-media"')
        doc = doc.replace(block, new)
        notes.append(slug)

    if doc != original and not dry:
        index.write_text(doc, encoding="utf-8")
    return notes


def main() -> int:
    p = argparse.ArgumentParser(description="Give the hand-written articles a real hero image.")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    built = set()
    for m in (ROOT / "tools" / "articles").glob("*.py"):
        if m.name.startswith("_"):
            continue
        s = re.search(r'"slug":\s*"([^"]+)"', m.read_text(encoding="utf-8"))
        if s:
            built.add(s.group(1))

    touched = 0
    for f in sorted(ARTICLES.glob("*.html")):
        if f.name == "index.html" or f.stem.lower() in built:
            continue
        notes = fix(f, args.dry_run)
        if notes:
            touched += 1
            print(f"  {f.stem}: {'; '.join(notes)}")
    print(f"\n{touched} hand-written article(s) "
          f"{'would be' if args.dry_run else ''} updated")

    cards = fix_index_cards(args.dry_run)
    print(f"{len(cards)} index card(s) "
          f"{'would be' if args.dry_run else ''} repointed at a self-hosted image")
    for c in cards:
        print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
