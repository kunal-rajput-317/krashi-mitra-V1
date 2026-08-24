# ============================================================
# services/article_publish.py
# लेख — publish an article from the admin panel, with no deploy
#
# WHY THIS EXISTS
# Until now an article could only be born from a git commit:
# tools/articles/<name>.py → tools/article_builder.py → frontend/articles/
# → push → Netlify build. That is fine at a laptop and impossible from a phone,
# and it means a topic worth writing today waits for a deploy window. This
# module is the same pipeline with the filesystem swapped for Postgres and the
# deploy swapped for a request.
#
# THE PAGE IS STILL BUILT BY tools/article_builder.py — the module itself,
# imported by path, not a copy of it. An admin-published article therefore gets
# byte-identical chrome to the 98 committed ones: the same shell, the same CSS,
# the same three JSON-LD blocks, the same FAQ schema generated from the visible
# markup, and the same validator that has been refusing broken pages since it
# was written. Change the design in SHELL_SOURCE and these pages follow on
# their next render, like every other article.
#
# POSTGRES IS THE SOURCE OF TRUTH, DISK IS A CACHE. Render's free tier wipes
# the filesystem on every restart and redeploy — profile avatars learned that
# the hard way and now live in Postgres too. So publish() writes the row first
# and the file second, and restore_all() re-lays every file at boot. The file
# still matters because everything else here reads the directory, not a table:
# sitemap.py, llms.txt, /articles/meta and the article hub all enumerate
# frontend/articles/*.html at request time. Put the file where they already
# look and no other module has to learn that DB articles exist.
#
# WHAT IS STILL A DEPLOY: frontend/_redirects. Netlify reads it as a static
# file, so the one-time proxy rules that send *unknown* /articles/ paths to the
# backend have to ship once. After that, publishing is deploy-free forever.
# ============================================================

from __future__ import annotations

import base64
import importlib.util
import io
import json
import re
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_BUILDER = None


# ── the builder, imported rather than reimplemented ─────────────────────────

def _builder():
    """tools/article_builder.py as a module.

    Imported by path because tools/ is a script directory, not a package. Cheap
    and cached: the module body only defines constants and functions, and the
    page shell is read lazily inside its own _load_shell().
    """
    global _BUILDER
    if _BUILDER is None:
        spec = importlib.util.spec_from_file_location(
            "km_article_builder", ROOT / "tools" / "article_builder.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _BUILDER = mod
    return _BUILDER


def paths() -> tuple[Path, Path, Path]:
    """(frontend, articles dir, article-images dir) — read off the builder so
    the panel and the CLI can never disagree about where an article lives."""
    b = _builder()
    return b.FRONTEND, b.ARTICLES, b.FRONTEND / "images" / "articles"


# ── categories ─────────────────────────────────────────────────────────────
#
# The key MUST be one of the filter chips in frontend/articles/index.html — a
# card carrying an id no chip filters on is invisible on the hub. The palette
# lives here so the panel never asks an author to pick hex codes.

CATS: dict[str, dict] = {
    "khad":      {"label": "खाद-उर्वरक", "emoji": "🧪", "accent": "#0369a1", "bg": "#eef6ff", "tag_bg": "#e0f2fe", "tag_color": "#0369a1"},
    "keet":      {"label": "फसल कीट",     "emoji": "🐛", "accent": "#b91c1c", "bg": "#fff1f1", "tag_bg": "#fee2e2", "tag_color": "#b91c1c"},
    "mausam":    {"label": "मौसम",        "emoji": "🌦️", "accent": "#0891b2", "bg": "#ecfeff", "tag_bg": "#cffafe", "tag_color": "#0e7490"},
    "ganna":     {"label": "गन्ना",       "emoji": "🎋", "accent": "#15803d", "bg": "#f0fdf4", "tag_bg": "#dcfce7", "tag_color": "#15803d"},
    "sabji":     {"label": "सब्जी",       "emoji": "🥬", "accent": "#4d7c0f", "bg": "#f7fee7", "tag_bg": "#ecfccb", "tag_color": "#4d7c0f"},
    "fruit":     {"label": "फल",          "emoji": "🥭", "accent": "#ea580c", "bg": "#fff7ed", "tag_bg": "#ffedd5", "tag_color": "#c2410c"},
    "anaaj":     {"label": "अनाज",        "emoji": "🌾", "accent": "#ca8a04", "bg": "#fff9e6", "tag_bg": "#fff4e0", "tag_color": "#ca8a04"},
    "ped":       {"label": "पेड़-वानिकी",  "emoji": "🌳", "accent": "#047857", "bg": "#ecfdf5", "tag_bg": "#d1fae5", "tag_color": "#047857"},
    "jankari":   {"label": "जानकारी",     "emoji": "📊", "accent": "#4338ca", "bg": "#eef2ff", "tag_bg": "#e0e7ff", "tag_color": "#4338ca"},
    "karnataka": {"label": "कर्नाटक",     "emoji": "📍", "accent": "#7c3aed", "bg": "#f5f3ff", "tag_bg": "#ede9fe", "tag_color": "#6d28d9"},
}

_HI_MONTHS = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून",
              "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]

# Lowercase only, and long enough to be a real URL: sitemap.py serves every
# article at stem.lower(), so a mixed-case name makes the canonical and the
# sitemap disagree about which URL is the real one.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{2,79}$")

# Reserved because routes/articles.py and routes/credits.py already answer at
# these paths — an article claiming one would shadow a live page.
RESERVED_SLUGS = {"index", "meta", "credits"}


class PublishError(ValueError):
    """A payload the panel must fix. Always a 400, never a 500."""


# ── markdown → the site's own section markup ───────────────────────────────
#
# The author writes markdown, not HTML. That is not a convenience: the article
# CSS has a fixed vocabulary (article-section / section-heading / article-table
# / tip-box), and hand-typed HTML in a textarea is exactly how an unclosed
# <div> ships — which on this site blanks the entire page on mobile while
# desktop still looks fine. Generated markup is balanced by construction.
#
#   ## 🐛 heading      → a new <section> with an icon + <h2>
#   ### heading        → <h3> inside the current section
#   - item / 1. item   → <ul> / <ol>
#   | a | b |          → <table class="article-table"> (a --- row is the rule)
#   > text             → tip-box info     💡
#   >! text            → tip-box warning  ⚠️  — doses, money, deadlines
#   >* text            → tip-box tip      🌱
#   **bold**  [t](url) → <strong> / <a>

_MD_INLINE = (
    (re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)"), r"<em>\1</em>"),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<a href="\2">\1</a>'),
)

_AD_LEADERBOARD = """
  <!-- ── AD SLOT ── -->
  <div class="ad-slot leaderboard" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="3367685932" data-format="auto"></div>
    </div>
  </div>
"""

_AD_RESPONSIVE = """
  <!-- ── AD SLOT ── -->
  <div class="ad-slot responsive" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="4489195916" data-format="auto"></div>
    </div>
  </div>
"""

_TIP = {">!": ("warning", "⚠️"), ">*": ("tip", "🌱"), ">": ("info", "💡")}

_SECTION_OPEN = '\n  <section class="article-section">'
_BLOCK_START = re.compile(r"^(#{2,3}\s|\||>|[-*+]\s|\d+[.)]\s)")


def _inline(s: str) -> str:
    s = s.strip()
    for pat, rep in _MD_INLINE:
        s = pat.sub(rep, s)
    return s


def md_to_html(md: str) -> str:
    """Markdown → the body HTML the shared article CSS already styles."""
    out: list[str] = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    open_section = False

    def close_section():
        nonlocal open_section
        if open_section:
            out.append('  </section>\n\n  <hr class="section-divider" />')
            open_section = False

    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped:
            i += 1
            continue

        # ## heading — opens a section. A leading emoji becomes the s-icon.
        if stripped.startswith("## "):
            close_section()
            text = stripped[3:].strip()
            icon, rest = "📌", text
            m = re.match(r"^([^\w\s<(\[]+)\s+(.+)$", text)
            if m:
                icon, rest = m.group(1), m.group(2)
            out.append(_SECTION_OPEN + "\n"
                       '    <div class="section-heading">\n'
                       f'      <span class="s-icon">{icon}</span>\n'
                       f'      <h2>{_inline(rest)}</h2>\n'
                       '    </div>')
            open_section = True
            i += 1
            continue

        if stripped.startswith("### "):
            out.append(f"    <h3>{_inline(stripped[4:])}</h3>")
            i += 1
            continue

        # | table |
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in
                             lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[1:]
            if body and all(re.fullmatch(r":?-{2,}:?", c or "-") for c in body[0]):
                body = body[1:]
            out.append('    <table class="article-table">')
            out.append("      <thead><tr>"
                       + "".join(f"<th>{_inline(c)}</th>" for c in head)
                       + "</tr></thead>")
            out.append("      <tbody>")
            for r in body:
                out.append("        <tr>"
                           + "".join(f"<td>{_inline(c)}</td>" for c in r)
                           + "</tr>")
            out.append("      </tbody>")
            out.append("    </table>")
            continue

        # > tip boxes
        if stripped.startswith(">"):
            marker = (">!" if stripped.startswith(">!")
                      else ">*" if stripped.startswith(">*") else ">")
            cls, icon = _TIP[marker]
            buf = []
            while i < len(lines) and lines[i].strip().startswith(marker):
                buf.append(lines[i].strip()[len(marker):].strip())
                i += 1
            out.append(f'    <div class="tip-box {cls}">\n'
                       f'      <span class="tip-icon">{icon}</span>\n'
                       f'      <div class="tip-content">{_inline(" ".join(buf))}</div>\n'
                       '    </div>')
            continue

        # - bullets / 1. numbers
        pat = (r"^[-*+]\s+(.*)$" if re.match(r"^[-*+]\s+", stripped)
               else r"^\d+[.)]\s+(.*)$" if re.match(r"^\d+[.)]\s+", stripped)
               else None)
        if pat:
            tag = "ul" if pat.startswith("^[-") else "ol"
            items = []
            while i < len(lines) and re.match(pat, lines[i].strip()):
                items.append(re.match(pat, lines[i].strip()).group(1))
                i += 1
            out.append(f"    <{tag}>")
            out += [f"      <li>{_inline(it)}</li>" for it in items]
            out.append(f"    </{tag}>")
            continue

        # paragraph — consecutive non-blank, non-block lines
        buf = []
        while (i < len(lines) and lines[i].strip()
               and not _BLOCK_START.match(lines[i].strip())):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"    <p>{_inline(' '.join(buf))}</p>")

    close_section()
    html = "\n".join(out)

    # Ads: one after the opening section, one around the middle. Never above the
    # fold, and never a raw AdSense <ins> — frontend/ads.js fills these markers.
    parts = html.split(_SECTION_OPEN)
    if len(parts) > 2:
        parts[1] += _AD_LEADERBOARD
    if len(parts) > 4:
        parts[len(parts) // 2] += _AD_RESPONSIVE
    return _SECTION_OPEN.join(parts)


# ── related cards, taken from articles that actually exist ─────────────────

def _related_pool() -> list[tuple]:
    """(href, accent, emoji, tag, title, cat) for every card on the hub.

    Read off frontend/articles/index.html rather than invented, because the
    builder's validator rejects an internal /articles/ link with no file behind
    it — and rightly: a dead related card is a dead end for the farmer and a
    soft-404 for Google.
    """
    _, articles, _ = paths()
    try:
        doc = (articles / "index.html").read_text(encoding="utf-8")
    except OSError:
        return []
    pool = []
    for m in re.finditer(
            r'<a class="article-card" href="([^"]+)"[^>]*data-cat="([^"]*)"'
            r'[^>]*style="--accent:([^"]+)"(.*?)</a>', doc, re.S):
        href, cat, accent, block = m.groups()
        slug = href.rsplit("/", 1)[-1].removesuffix(".html")
        if not (articles / f"{slug}.html").is_file():
            continue
        emoji = re.search(r'article-media-emoji">([^<]+)<', block)
        tag = re.search(r'class="article-tag"[^>]*>([^<]+)<', block)
        title = re.search(r'class="article-title">([^<]+)<', block)
        pool.append((f"https://krashimitra.in/articles/{slug}", accent.strip(),
                     (emoji.group(1) if emoji else "🌾").strip(),
                     (tag.group(1) if tag else "लेख").strip(),
                     (title.group(1) if title else slug).strip(),
                     cat.strip()))
    return pool


def _related(cat: str, slug: str, given) -> list[tuple]:
    if given:
        return [tuple(r) for r in given]
    pool = [p for p in _related_pool() if not p[0].endswith(f"/{slug}")]
    same = [p[:5] for p in pool if p[5] == cat][:3]
    rest = [p[:5] for p in pool if p[5] != cat][:max(0, 4 - len(same))]
    return (same + rest)[:4] + [
        ("https://krashimitra.in/bhav/", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "आज का मंडी भाव — राज्यवार LIVE रेट"),
        ("https://krashimitra.in/chat", "#2e7d32", "🤖", "AI · सहायता",
         "फसल की फोटो भेजें — AI से तुरंत पहचान व इलाज"),
    ]


# ── payload → the full ARTICLE dict the builder wants ──────────────────────

def expand(payload: dict) -> dict:
    """The panel's short form → every key tools/article_builder.py requires.

    The panel asks only for what a human knows (topic, title, body, FAQs,
    category). Read time, word count, schema copy, card palette, breadcrumb and
    related cards are all derived, because a field the author must re-enter
    correctly every time is a field that goes stale on one article and is never
    noticed again.
    """
    slug = (payload.get("slug") or "").strip().lower()
    if not SLUG_RE.match(slug) or slug in RESERVED_SLUGS:
        raise PublishError("slug: सिर्फ़ a-z, 0-9 और '-' (3–80 अक्षर), "
                           "और index/meta/credits नहीं")

    cat = (payload.get("cat") or "jankari").strip()
    if cat not in CATS:
        raise PublishError(f"cat: '{cat}' कोई फ़िल्टर चिप नहीं है — {', '.join(CATS)}")
    pal = CATS[cat]

    title = (payload.get("title") or "").strip()
    desc = (payload.get("description") or "").strip()
    h1 = (payload.get("h1") or title).strip()
    if not (title and desc and h1):
        raise PublishError("title, description और h1 — तीनों चाहिए")

    body_raw = payload.get("body") or ""
    body = md_to_html(body_raw) if payload.get("body_format") == "md" else body_raw
    if not body.strip():
        raise PublishError("body खाली है")

    faqs = [(str(q).strip(), str(a).strip())
            for q, a in (payload.get("faqs") or [])
            if str(q).strip() and str(a).strip()]

    d = str(payload.get("date") or date.today().isoformat())[:10]
    try:
        dt = date.fromisoformat(d)
    except ValueError:
        raise PublishError("date: YYYY-MM-DD चाहिए")
    date_label = payload.get("date_label") or f"{_HI_MONTHS[dt.month - 1]} {dt.year}"

    words = len(re.sub(r"<[^>]+>", " ", body).split()) + sum(
        len(f"{q} {a}".split()) for q, a in faqs)
    read_time = int(payload.get("read_time") or max(3, round(words / 200)))

    kw = (payload.get("keywords") or "").strip() or title
    card_in = payload.get("card") or {}

    # The hero is whatever image the panel put on disk under this slug — one
    # key feeding the <figure>, og:image, the schema image and the hub card,
    # exactly as the content modules do it.
    _, _, images = paths()
    hero = None
    for ext in ("webp", "jpg", "jpeg", "png"):
        if (images / f"{slug}.{ext}").is_file():
            hero = (f"images/articles/{slug}.{ext}",
                    (payload.get("image_alt") or h1).strip(),
                    (payload.get("image_caption") or "").strip())
            break

    a = {
        "slug": slug,
        "date": d,
        "date_modified": str(payload.get("date_modified")
                             or date.today().isoformat())[:10],
        "date_label": date_label,
        "read_time": read_time,
        "word_count": words,
        "lang": payload.get("lang") or "hi",
        "section": payload.get("section") or pal["label"],
        "cat_label": payload.get("cat_label") or pal["label"],
        "cat_query": cat,
        "breadcrumb_leaf": (payload.get("breadcrumb_leaf") or h1)[:40],
        "title": title,
        "description": desc,
        "keywords": kw,
        "og_title": payload.get("og_title") or f"{title} | KrashiMitra.in",
        "og_desc": payload.get("og_desc") or desc,
        "headline": payload.get("headline") or h1,
        "headline_en": payload.get("headline_en") or payload.get("h1_en") or h1,
        "schema_desc": payload.get("schema_desc") or desc,
        "schema_keywords": [k.strip() for k in kw.split(",") if k.strip()],
        "h1": h1,
        "h1_en": (payload.get("h1_en") or "").strip(),
        "share_title": payload.get("share_title") or h1,
        "hero_excerpt": payload.get("hero_excerpt") or desc,
        "lede_h2": payload.get("lede_h2") or "एक नज़र में",
        "badges": [tuple(b) for b in (payload.get("badges") or [])] or [
            ("badge-season", f"🗓️ {date_label}"),
            ("badge-location", f"{pal['emoji']} {pal['label']}"),
        ],
        "quick_facts": [tuple(f) for f in (payload.get("quick_facts") or [])] or [
            ("", "🗓️", date_label, "प्रकाशित"),
            ("", "⏱️", f"{read_time} मिनट", "पढ़ने का समय"),
            ("", pal["emoji"], pal["label"], "श्रेणी"),
        ],
        "body": body,
        "faqs": faqs,
        "bhav_links": [tuple(x) for x in (payload.get("bhav_links") or [])],
        "related": _related(cat, slug, payload.get("related")),
        "card": {
            "emoji": card_in.get("emoji") or pal["emoji"],
            "bg": card_in.get("bg") or pal["bg"],
            "accent": card_in.get("accent") or pal["accent"],
            "tag": card_in.get("tag") or pal["label"],
            "tag_bg": card_in.get("tag_bg") or pal["tag_bg"],
            "tag_color": card_in.get("tag_color") or pal["tag_color"],
            "title": card_in.get("title") or h1,
            "cats": card_in.get("cats") or cat,
            "keywords": card_in.get("keywords") or kw,
        },
    }
    if hero:
        a["hero_image"] = hero
    return a


def render_html(payload: dict) -> str:
    """The finished page.

    SystemExit is how the builder fails a CLI run; inside a request it would
    unwind past the exception middleware, so it is caught and turned into the
    400 the panel can actually show.
    """
    try:
        return _builder().render(expand(payload))
    except PublishError:
        raise
    except SystemExit as e:
        raise PublishError(str(e))


# ── hero image ─────────────────────────────────────────────────────────────

def store_image(raw: bytes) -> tuple[bytes, bytes]:
    """(1200×675 hero, 480×270 card cut) as WebP — the same two cuts
    tools/fetch_article_images.py writes, so /articles/meta's card-cut lookup
    finds the small one and the hub does not ship a 1200px file into a 360px
    band."""
    try:
        from PIL import Image
    except ImportError:                       # pragma: no cover - Pillow is pinned
        raise PublishError("Pillow नहीं मिला — इमेज बदली नहीं जा सकती")

    def cut(size: tuple[int, int]) -> bytes:
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGB")
        tw, th = size
        # centre crop to the target ratio, then resize — never squash, a
        # stretched field photo reads as a broken page.
        ratio, want = im.width / im.height, tw / th
        if ratio > want:
            w = int(im.height * want)
            im = im.crop(((im.width - w) // 2, 0, (im.width - w) // 2 + w, im.height))
        else:
            h = int(im.width / want)
            im = im.crop((0, (im.height - h) // 2, im.width, (im.height - h) // 2 + h))
        im = im.resize(size, Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=82, method=4)
        return buf.getvalue()

    try:
        return cut((1200, 675)), cut((480, 270))
    except PublishError:
        raise
    except Exception as e:
        raise PublishError(f"इमेज पढ़ी नहीं जा सकी: {e}")


def _write_images(slug: str, hero_b64: str | None, card_b64: str | None) -> None:
    """Lay the stored WebP bytes back down on disk under the slug.

    Called on every publish and again at boot, because the bytes in Postgres
    are the only copy that survives a Render restart — and the builder refuses
    to render a hero_image that is not on disk.
    """
    _, _, images = paths()
    images.mkdir(parents=True, exist_ok=True)
    if hero_b64:
        (images / f"{slug}.webp").write_bytes(base64.b64decode(hero_b64))
    if card_b64:
        (images / f"{slug}-card.webp").write_bytes(base64.b64decode(card_b64))


# ── writing the article into the site ──────────────────────────────────────

def materialize(row) -> Path:
    """Write one stored article into frontend/articles/, card and all.

    Re-renders from the payload rather than replaying row.html so a design
    change in SHELL_SOURCE reaches these pages too; falls back to the stored
    HTML if the re-render fails, because a page that is one release out of date
    beats a page that 404s. A raw-HTML article has no payload and is always
    written verbatim.
    """
    _, articles, _ = paths()
    articles.mkdir(parents=True, exist_ok=True)
    out = articles / f"{row.slug}.html"

    # Images before the render: the builder refuses a hero_image that is not on
    # disk, and after a restart Postgres holds the only copy.
    _write_images(row.slug, row.image_data, row.image_card_data)

    payload = json.loads(row.payload) if row.payload else None
    if payload:
        try:
            a = expand(payload)
            out.write_text(_builder().render(a), encoding="utf-8")
            _builder().sync_index_card(a)
            return out
        except (SystemExit, Exception):
            pass                    # fall through to the last-rendered copy

    if not row.html:
        raise PublishError(f"{row.slug}: कुछ भी सेव नहीं है")
    out.write_text(row.html, encoding="utf-8")
    return out


def validate_file(slug: str) -> list[str]:
    """The builder's own checks, run on the file we just wrote."""
    _, articles, _ = paths()
    path = articles / f"{slug}.html"
    if not path.is_file():
        return ["page not written"]
    return _builder().validate(path)


def unmaterialize(slug: str) -> None:
    """Remove the page, its images and its hub card from disk."""
    _, articles, images = paths()
    for p in (articles / f"{slug}.html",
              images / f"{slug}.webp", images / f"{slug}-card.webp"):
        try:
            p.unlink()
        except OSError:
            pass
    index = articles / "index.html"
    try:
        doc = index.read_text(encoding="utf-8")
    except OSError:
        return
    trimmed = re.sub(
        rf'[ \t]*<!--[^\n]*-->\n[ \t]*<a class="article-card" '
        rf'href="{re.escape(slug)}(?:\.html)?".*?</a>\n',
        "", doc, flags=re.S)
    # The builder inserts a card as "\n" + card at the top of the list, so
    # removing the card again leaves its blank line behind. One publish is
    # nothing; a page republished and pulled a few times would walk the whole
    # list down the file, and every one of those lines is a diff against the
    # committed index.html for as long as it lives.
    trimmed = re.sub(r'(<div class="articles-list" id="articles-list">\n)\n+',
                     r"\1\n", trimmed)
    if trimmed != doc:
        index.write_text(_builder()._sync_index_count(trimmed), encoding="utf-8")


# ── store (Postgres) ───────────────────────────────────────────────────────

def get(db, slug: str):
    from backend.database.db import PublishedArticle
    return db.query(PublishedArticle).filter(
        PublishedArticle.slug == slug).first()


def listing(db) -> list[dict]:
    """Every admin-published article, newest first, plus how it stands on disk.

    `on_disk` is not decoration. A row that is live in Postgres but missing
    from frontend/articles/ means the boot restore did not run or failed, and
    the URL is 404ing right now — that is precisely the state this panel has to
    be able to show.
    """
    from backend.database.db import PublishedArticle
    _, articles, _ = paths()
    rows = (db.query(PublishedArticle)
              .order_by(PublishedArticle.updated_at.desc()).all())
    out = []
    for r in rows:
        out.append({
            "slug": r.slug,
            "title": r.title or r.slug,
            "cat": r.cat or "",
            "status": r.status,
            "words": r.word_count or 0,
            "has_image": bool(r.image_mime),
            "url": f"https://krashimitra.in/articles/{r.slug}",
            "on_disk": (articles / f"{r.slug}.html").is_file(),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return out


def committed_slugs() -> set[str]:
    """Articles that came from git, i.e. everything already static on Netlify."""
    _, articles, _ = paths()
    return {p.stem.lower() for p in articles.glob("*.html") if p.stem != "index"}


def _refuse_if_committed(row, slug: str) -> None:
    """Never write over an article this panel did not publish.

    A page already on disk that has no payload behind it came from git. Writing
    over it would put two different articles at one URL — and the committed one
    would come back at the next deploy anyway, so whichever a reader got would
    depend on when they arrived. The draft row that an image upload creates is
    NOT ownership: without this check, uploading a photo under a committed
    slug would be enough to make the next publish overwrite that article.
    """
    _, articles, _ = paths()
    if not (articles / f"{slug}.html").is_file():
        return
    if row is not None and (row.payload or row.html):
        return                                 # ours already — this is an update
    raise PublishError(
        f"/articles/{slug} पहले से मौजूद है (git से आया लेख) — "
        "दूसरा slug चुनें, वरना दोनों एक ही URL पर होंगे")


def save(db, payload: dict, *, force: bool = False) -> dict:
    """Render → write → validate → store. Postgres last, so nothing is
    recorded as published unless the page it describes actually built.

    `force` ships a page the validator complained about. It exists because the
    validator encodes editorial rules (2,000+ words, 6 FAQs, a hero photo) as
    well as correctness rules, and the author — not this module — decides when
    a short scheme update is worth publishing anyway. The complaints are stored
    with the row either way, so a forced page is never a silent one.
    """
    from backend.database.db import PublishedArticle

    slug = (payload.get("slug") or "").strip().lower()
    row = get(db, slug)
    _refuse_if_committed(row, slug)

    # Images next: the builder refuses a hero_image that is not on disk, and
    # after a restart the only copy of it is the one in Postgres. Do this
    # before expand(), which decides whether the article has a hero at all.
    if row is not None:
        _write_images(slug, row.image_data, row.image_card_data)

    a = expand(payload)                        # raises PublishError on bad input
    slug = a["slug"]

    _, articles, _ = paths()
    existing = articles / f"{slug}.html"

    try:
        html = _builder().render(a)
    except SystemExit as e:                    # a CLI abort, inside a request
        raise PublishError(str(e))
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text(html, encoding="utf-8")
    problems = validate_file(slug)
    if problems and not force:
        # Leave nothing behind that the site would serve: sitemap.py enumerates
        # this directory, so a rejected page would be handed to Google anyway.
        try:
            existing.unlink()
        except OSError:
            pass
        if row is not None and (row.payload or row.html):
            try:
                materialize(row)               # put the last good version back
            except Exception:
                pass
        return {"ok": False, "slug": slug, "problems": problems}

    _builder().sync_index_card(a)

    now = datetime.utcnow()
    if row is None:
        row = PublishedArticle(slug=slug, created_at=now)
        db.add(row)
    row.title = a["title"]
    row.cat = a["cat_query"]
    row.payload = json.dumps(payload, ensure_ascii=False)
    row.html = html
    row.word_count = a["word_count"]
    row.status = "live"
    row.problems = json.dumps(problems, ensure_ascii=False) if problems else None
    row.updated_at = now
    db.commit()

    return {"ok": True, "slug": slug, "problems": problems,
            "url": f"https://krashimitra.in/articles/{slug}",
            "words": a["word_count"]}


def attach_image(db, slug: str, raw: bytes) -> dict:
    """Store a hero photo for an article — in Postgres, and on disk.

    Postgres because Render's disk is wiped on restart and a hero that
    disappears takes og:image, the schema image and the hub card's picture with
    it. On disk because the builder validates hero_image against the filesystem.
    """
    from backend.database.db import PublishedArticle

    row = get(db, slug)
    # Before Pillow does any work: this writes frontend/images/articles/<slug>,
    # which for a committed slug is a photo somebody sourced and licensed.
    _refuse_if_committed(row, slug)

    hero, card = store_image(raw)
    if row is None:
        row = PublishedArticle(slug=slug, status="draft",
                               created_at=datetime.utcnow())
        db.add(row)
    row.image_data = base64.b64encode(hero).decode()
    row.image_card_data = base64.b64encode(card).decode()
    row.image_mime = "image/webp"
    row.updated_at = datetime.utcnow()
    db.commit()
    _write_images(slug, row.image_data, row.image_card_data)
    return {"ok": True, "slug": slug,
            "path": f"images/articles/{slug}.webp",
            "bytes": len(hero), "card_bytes": len(card)}


def delete(db, slug: str) -> dict:
    """Unpublish: the row goes, the page goes, the card goes.

    The URL then 404s rather than soft-404ing on a homepage — which is what the
    /* catch-all in _redirects is for, and what stops Google holding an empty
    page in the index.
    """
    row = get(db, slug)
    if row is None:
        raise PublishError(f"{slug}: कोई पैनल-लेख नहीं")
    db.delete(row)
    db.commit()
    unmaterialize(slug)
    return {"ok": True, "slug": slug}


def restore_all(db) -> dict:
    """Re-lay every published article on disk. Runs at boot.

    This is the whole reason the feature survives a deploy: Render replaces the
    filesystem with a fresh git checkout on every restart, so without this the
    panel's articles would quietly vanish from /articles/, from the sitemap and
    from Google — the way avatars vanished before they moved into Postgres.
    """
    from backend.database.db import PublishedArticle
    rows = (db.query(PublishedArticle)
              .filter(PublishedArticle.status == "live")
              .order_by(PublishedArticle.created_at.asc()).all())
    done, failed = [], []
    for r in rows:
        try:
            materialize(r)
            done.append(r.slug)
        except Exception as e:                 # one bad row must not stop boot
            failed.append(f"{r.slug}: {e}")
    return {"restored": done, "failed": failed}
