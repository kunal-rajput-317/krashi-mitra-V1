# ============================================================
# tools/article_journey.py
# The "आगे क्या करें" strip on the article pages the builder cannot reach.
#
# tools/article_builder.py renders the strip into every article it generates,
# from backend/services/ecosystem.py. But 36 of the 175 live articles predate
# the builder and have no content module, so render() can never see them —
# the same gap article_advisory.py and article_cards.py were written to close,
# closed the same way and run from the same --all.
#
# Everything the strip needs is already IN the built page, because that is what
# ecosystem.py's own article index reads: the headline, the articleSection, the
# /bhav price chips the author verified, and the declared <html lang>. So this
# sweep does not need a content module — it reads the page, works out what the
# page is about, and writes the strip back.
#
# WHERE IT GOES, in the order the page is likely to offer an anchor:
#   1. over the old hardcoded three-link CTA (chat/shop/weather, identical on
#      every page, pointing at the .html forms that 301) — 29 of the 36 have
#      it, and replacing it is strictly better than adding a second block
#   2. failing that, directly above the price-chip strip
#   3. failing that, directly above the canonical footer
# A page offering none of the three is left untouched and reported, rather than
# guessed at.
#
# Idempotent: a page already carrying the strip is skipped, so this is safe to
# run over the whole directory after a build.
# ============================================================

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services import ecosystem  # noqa: E402

SITE = "https://krashimitra.in"

MARK = 'class="km-journey"'          # presence = this page is already done

_RE = {
    "head":  re.compile(r'"headline"\s*:\s*"([^"]+)"'),
    "title": re.compile(r"<title>(.*?)</title>", re.S),
    "lang":  re.compile(r'<html[^>]*\blang="([a-z-]+)"'),
    "sect":  re.compile(r'"articleSection"\s*:\s*"([^"]+)"'),
    "cat":   re.compile(r'"breadcrumb"[^>]*>.*?</nav>', re.S),
    "chips": re.compile(r'<section class="bhav-links".*?</section>', re.S),
    "bhav":  re.compile(r"/bhav/([a-z0-9-]+)"),
    "cta":   re.compile(r"<!--\s*[^\n]*INTERNAL LINKS CTA.*?</section>", re.S),
    "foot":  re.compile(r"<!--\s*[^\n]*CANONICAL FOOTER", re.S),
    "js":    re.compile(r'km-journey\.js'),
}

_JS = '<script src="../km-journey.js" defer></script>\n'


def context_of(doc: str, slug: str) -> ecosystem.Ctx:
    """What this built page is about — read off the page itself.

    The crop comes from the price-chip strip and nowhere else. Every other
    /bhav link on an article sits in the related-articles cards, which are
    about OTHER articles; counting those files a mustard page under wheat.
    """
    m = _RE["head"].search(doc) or _RE["title"].search(doc)
    title = " ".join(m.group(1).split()) if m else ""
    lm = _RE["lang"].search(doc)
    sm = _RE["sect"].search(doc)
    chips = _RE["chips"].search(doc)
    crops = [c for c in _RE["bhav"].findall(chips.group(0) if chips else "")
             if c != "rajya"]
    crop = crops[0] if crops else ""
    return ecosystem.parse(
        f"{SITE}/articles/{slug}",
        section="articles",
        crop=crop,
        crop_hi=ecosystem.family_hi(ecosystem.family(crop)),
        topics=ecosystem.topics(sm.group(1) if sm else "", title),
        lang=(lm.group(1) if lm else "hi").split("-")[0],
        # Same reasoning as the builder: the related-articles grid and the
        # price chips are already on the page, so spending a slot on either
        # would restate a link the reader can see instead of opening the
        # sections he has no route to at all.
        have={"articles"} | ({"bhav"} if crops else set()),
    )


def ensure_in_html(doc: str, slug: str) -> tuple[str, bool]:
    """(document, changed). Never raises — a page that cannot be placed is
    returned untouched, which is what "changed=False" means to the caller."""
    if MARK in doc:
        return doc, False
    strip = ecosystem.journey_html(context_of(doc, slug))
    if not strip:
        return doc, False
    block = ('\n<!-- आगे क्या करें — backend/services/ecosystem.py -->\n'
             '<div style="max-width:860px;margin:0 auto 32px;padding:0 16px">'
             f'{strip}</div>\n')

    cta = _RE["cta"].search(doc)
    if cta:
        out = doc[:cta.start()] + block.strip("\n") + doc[cta.end():]
    else:
        chips = _RE["chips"].search(doc)
        anchor = chips or _RE["foot"].search(doc)
        if not anchor:
            return doc, False
        out = doc[:anchor.start()] + block + doc[anchor.start():]

    if not _RE["js"].search(out):
        # Beside the other deferred page scripts, immediately before </body>.
        i = out.rfind("</body>")
        out = (out[:i] + _JS + out[i:]) if i != -1 else out + _JS
    return out, True


def sweep(articles_dir=None, write: bool = True) -> list:
    """Add the strip to every built article page that has none. Idempotent."""
    d = pathlib.Path(articles_dir or (ROOT / "frontend" / "articles"))
    changed = []
    for p in sorted(d.glob("*.html")):
        if p.stem == "index":
            continue
        doc = p.read_text(encoding="utf-8", errors="replace")
        new, did = ensure_in_html(doc, p.stem.lower())
        if did:
            changed.append(p.stem)
            if write:
                p.write_text(new, encoding="utf-8")
    return changed


def unplaceable(articles_dir=None) -> list:
    """Pages with no strip and no anchor to hang one on — the ones a human has
    to look at. Reported separately from "changed" so a silent no-op cannot be
    mistaken for success."""
    d = pathlib.Path(articles_dir or (ROOT / "frontend" / "articles"))
    out = []
    for p in sorted(d.glob("*.html")):
        if p.stem == "index":
            continue
        doc = p.read_text(encoding="utf-8", errors="replace")
        if MARK in doc:
            continue
        if not ensure_in_html(doc, p.stem.lower())[1]:
            out.append(p.stem)
    return out


# A strip baked into a page keeps the look it had on the day it was written —
# its own inline <style> and its own icons. restyle() brings every baked strip
# up to ecosystem.py's current CSS and section photos without touching which
# links it carries, so a change to the strip's look reaches all 184 pages from
# the same --all run that builds them.
_STYLE_RE = re.compile(r"<style>\s*\.km-journey\{.*?</style>", re.S)
_ICO_RE = re.compile(r'(data-km-step="([a-z]+)"[^>]*>)'
                     r'<span class="km-journey-ico" aria-hidden="true">.*?</span>', re.S)


def restyle_html(doc: str) -> str:
    if MARK not in doc:
        return doc
    doc = _STYLE_RE.sub(lambda m: f"<style>{ecosystem.CSS}</style>", doc, count=1)

    def ico(m):
        sec = ecosystem.SECTIONS.get(m.group(2))
        img = ecosystem._ico(sec.icon) if sec else ""
        return f'{m.group(1)}<span class="km-journey-ico" aria-hidden="true">{img}</span>'
    doc = _ICO_RE.sub(ico, doc)
    return doc.replace('<div class="km-journey-h"><strong>🧭 ',
                       '<div class="km-journey-h"><strong>')


def restyle(articles_dir=None, write: bool = True) -> list:
    """Pages whose baked strip was out of date (and, with write, now is not)."""
    d = pathlib.Path(articles_dir or (ROOT / "frontend" / "articles"))
    changed = []
    for p in sorted(d.glob("*.html")):
        doc = p.read_text(encoding="utf-8", errors="replace")
        new = restyle_html(doc)
        if new != doc:
            changed.append(p.stem)
            if write:
                p.write_text(new, encoding="utf-8")
    return changed


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description='Add the "आगे क्या करें" strip to built article pages.')
    ap.add_argument("--check", action="store_true",
                    help="report what is missing, write nothing")
    ap.add_argument("--dir", type=pathlib.Path,
                    default=ROOT / "frontend" / "articles")
    args = ap.parse_args()

    hit = sweep(args.dir, write=not args.check)
    verb = "would add to" if args.check else "added to"
    print(f"journey strip {verb} {len(hit)} page(s)")
    for s in hit:
        print(f"  {s}")
    stuck = unplaceable(args.dir)
    if stuck:
        print(f"\nno anchor found on {len(stuck)} page(s) — look at these:")
        for s in stuck:
            print(f"  {s}")
    sys.exit(1 if (args.check and hit) or stuck else 0)
