# ============================================================
# KrashiMitra — article builder
#
# An article page is ~1,780 lines, of which ~1,500 are the shared page shell,
# the inline CSS and three JSON-LD blocks. Hand-writing that per article does
# not scale and it drifts: hand-written FAQ schema had already gone out of sync
# with the visible FAQ on eleven pages, and four articles shipped without their
# _redirects rule, so their .html form stayed live as a duplicate URL.
#
# So the boilerplate is not authored any more — it is DERIVED. An author (human
# or AI) writes one content module: metadata, body HTML, FAQ list, card. This
# builder produces the page and wires it into the site:
#
#   python tools/article_builder.py tools/articles/my_article.py
#   python tools/article_builder.py --all        # re-emit every article
#   python tools/article_builder.py --check      # validate, write nothing
#
# What it does, so no step can be forgotten:
#   1. renders the page from the shell + CSS of SHELL_SOURCE (a real article, so
#      the template can never fall behind the live site design)
#   2. generates the FAQPage JSON-LD *from the visible FAQ markup* — one source,
#      so the two cannot disagree
#   3. inserts/updates the card in frontend/articles/index.html
#   4. rebuilds the article 301 block in frontend/_redirects from disk
#   5. validates the result and fails loudly rather than shipping a broken page
#
# sitemap.xml, llms.txt and /articles/meta already enumerate the articles
# directory at request time, so they need nothing here.
#
# See tools/ARTICLE-TEMPLATE.md for the authoring rules and the content schema.
# ============================================================

from __future__ import annotations

import argparse
import html as htmllib
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
ARTICLES = FRONTEND / "articles"
INDEX = ARTICLES / "index.html"
REDIRECTS = FRONTEND / "_redirects"
CONTENT_DIR = Path(__file__).resolve().parent / "articles"

SITE = "https://krashimitra.in"

# The page whose shell + CSS every generated article inherits. It is a real,
# live article on purpose: change the site design there and every article
# rebuilt afterwards picks it up. If you retire this file, point this at
# another article and run --all.
SHELL_SOURCE = ARTICLES / "tomato-leaf-curl.html"

REQUIRED_KEYS = (
    "slug date date_label read_time word_count section cat_label cat_query "
    "breadcrumb_leaf title description keywords og_title og_desc "
    "headline headline_en schema_desc schema_keywords h1 h1_en share_title "
    "hero_excerpt lede_h2 badges quick_facts body faqs bhav_links related card"
).split()

REQUIRED_CARD_KEYS = "emoji bg accent tag tag_bg tag_color title cats keywords".split()

# Where an article with no photograph of its own falls back to. Used for
# og:image only — it is deliberately NOT rendered on the page, because a
# generic site banner sitting where the subject should be is worse than no
# image at all.
FALLBACK_OG = f"{SITE}/images/og-banner.jpg"


# Everything on the page that has to agree about what language it is in.
#
# The builder used to hardcode Hindi in five separate places — <html lang>,
# hreflang, og:locale, schema inLanguage and the breadcrumb words. The two
# Kannada Karnataka articles predate the builder and set all five by hand,
# which is the only reason they were right; anything built here would have
# declared itself Hindi while showing Kannada, and a page whose declared
# language contradicts its text is not eligible for the query family it was
# written for. So the five are one table, keyed by ARTICLE["lang"].
#
# `fonts` is the Google Fonts family list: a Devanagari webfont does not carry
# Kannada glyphs, so a kn page without this falls back to whatever the phone
# happens to have.
LOCALES = {
    "hi": {
        "fonts": "family=Noto+Serif+Devanagari:wght@400;600;700",
        "home": "मुख्य", "articles": "लेख", "all_prices": "सभी फसलों के भाव →",
        "read": "मिनट पढ़ें", "share": "शेयर", "print": "प्रिंट",
        "copied": "लिंक कॉपी हो गया!", "ad": "विज्ञापन",
        "faq_h2": "अक्सर पूछे जाने वाले सवाल",
        "cta_h3": "KrashiMitra.in — आपका विश्वसनीय कृषि साथी",
        "cta_p": "मंडी भाव, सरकारी योजनाएं, बीज-खाद की जानकारी और फसल रोग उपचार — सब कुछ हिंदी में।",
        "cta_a": "KrashiMitra.in पर जाएं →",
        "related_h": "संबंधित लेख", "all_articles": "सभी लेख देखें →",
        "bhav_h2": "📊 आज का ताज़ा मंडी भाव",
        "wa_share": "📲 यह लेख WhatsApp पर भेजें",
    },
    "kn": {
        "fonts": "family=Tiro+Kannada&family=Noto+Serif+Kannada:wght@400;600;700",
        "home": "ಮುಖ್ಯ", "articles": "ಲೇಖನಗಳು", "all_prices": "ಎಲ್ಲಾ ಬೆಳೆಗಳ ದರ →",
        "read": "ನಿಮಿಷ ಓದು", "share": "ಹಂಚಿ", "print": "ಮುದ್ರಿಸಿ",
        "copied": "ಲಿಂಕ್ ನಕಲಾಗಿದೆ!", "ad": "ಜಾಹೀರಾತು",
        "faq_h2": "ಪದೇ ಪದೇ ಕೇಳುವ ಪ್ರಶ್ನೆಗಳು",
        "cta_h3": "KrashiMitra.in — ನಿಮ್ಮ ವಿಶ್ವಾಸಾರ್ಹ ಕೃಷಿ ಸಂಗಾತಿ",
        "cta_p": "ಮಾರುಕಟ್ಟೆ ದರ, ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು, ಬಿತ್ತನೆ ಬೀಜ ಮತ್ತು ಗೊಬ್ಬರದ ಮಾಹಿತಿ, ಬೆಳೆ ರೋಗ ಚಿಕಿತ್ಸೆ — ಎಲ್ಲವೂ ಕನ್ನಡದಲ್ಲಿ.",
        "cta_a": "KrashiMitra.in ಗೆ ಹೋಗಿ →",
        "related_h": "ಸಂಬಂಧಿತ ಲೇಖನಗಳು", "all_articles": "ಎಲ್ಲಾ ಲೇಖನಗಳು →",
        "bhav_h2": "📊 ಇಂದಿನ ಮಾರುಕಟ್ಟೆ ದರ",
        "wa_share": "📲 ಈ ಲೇಖನವನ್ನು WhatsApp ನಲ್ಲಿ ಕಳುಹಿಸಿ",
    },
    "ta": {
        "fonts": "family=Noto+Serif+Tamil:wght@400;600;700",
        "home": "முகப்பு", "articles": "கட்டுரைகள்",
        "all_prices": "அனைத்துப் பயிர் விலைகள் →",
        "read": "நிமிடம் படிக்க", "share": "பகிர்", "print": "அச்சிடு",
        "copied": "இணைப்பு நகலெடுக்கப்பட்டது!", "ad": "விளம்பரம்",
        "faq_h2": "அடிக்கடி கேட்கப்படும் கேள்விகள்",
        "cta_h3": "KrashiMitra.in — உங்கள் நம்பகமான வேளாண் நண்பன்",
        "cta_p": "சந்தை விலை, அரசுத் திட்டங்கள், விதை-உரத் தகவல், பயிர் நோய்க்கான தீர்வு — அனைத்தும் தமிழில்.",
        "cta_a": "KrashiMitra.in-க்குச் செல்லுங்கள் →",
        "related_h": "தொடர்புடைய கட்டுரைகள்", "all_articles": "அனைத்துக் கட்டுரைகள் →",
        "bhav_h2": "📊 இன்றைய சந்தை விலை",
        "wa_share": "📲 இந்தக் கட்டுரையை WhatsApp-இல் அனுப்பு",
    },
}


# ── shared chunks, lifted from the live shell source ────────────────────────

def _chunk(text: str, start: str, end: str, keep_end: bool = True) -> str:
    try:
        i = text.index(start)
        j = text.index(end, i)
    except ValueError:  # pragma: no cover - only when SHELL_SOURCE changes shape
        raise SystemExit(
            f"article_builder: could not find {start!r}…{end!r} in "
            f"{SHELL_SOURCE.name}. The shell source changed shape — update the "
            f"markers in article_builder.py."
        )
    return text[i:j + (len(end) if keep_end else 0)]


def _load_shell() -> dict:
    if not SHELL_SOURCE.is_file():
        raise SystemExit(f"article_builder: SHELL_SOURCE missing: {SHELL_SOURCE}")
    t = SHELL_SOURCE.read_text(encoding="utf-8")
    return {
        "style": _chunk(t, "  <style>\n    :root {", "  </style>"),
        "header": _chunk(t, "<!-- ══ CANONICAL HEADER",
                         '<div class="topbar-spacer" id="topbar-spacer"></div>'),
        "cta": _chunk(t, "<!-- ═══ INTERNAL LINKS CTA", "</section>"),
        "tail": t[t.index("<!-- ══ CANONICAL FOOTER"):],
    }


# ── helpers ────────────────────────────────────────────────────────────────

def _plain(s: str) -> str:
    """Visible text of a fragment — what the JSON-LD twin must say."""
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _canonical(slug: str) -> str:
    # sitemap.py serves every article at f.stem.lower(); the canonical must match
    # it exactly or the two disagree about which URL is the real one.
    return f"{SITE}/articles/{slug.lower()}"


# ── hero image ─────────────────────────────────────────────────────────────
#
# One optional key, `hero_image`, feeds all four places an article's picture has
# to appear: the <figure> on the page, og:image, the Article schema image, and
# the card on /articles/. They used to be independent, which is how 44 articles
# ended up declaring the generic site banner as their og:image while showing no
# picture at all and rendering an emoji on the index.
#
#   "hero_image": ("images/articles/foo.webp", "alt text", "caption"),
#
# The path is frontend-relative and must exist on disk: a missing static file is
# served as the 200-HTML fallback, not a 404, so a typo would fail silently.

def _hero(a: dict) -> tuple[str, str, str] | None:
    h = a.get("hero_image")
    if not h:
        return None
    if isinstance(h, str):
        h = (h, a.get("h1_en") or a.get("h1", ""), "")
    path, alt, caption = (list(h) + ["", ""])[:3]
    path = path.lstrip("/")
    if not (FRONTEND / path).is_file():
        raise SystemExit(f"article_builder: {a['slug']} hero_image not on disk: "
                         f"frontend/{path}")
    return path, alt, caption


def _card_cut(rel: str) -> str:
    """The 480px variant of a hero, when fetch_article_images.py made one.

    Mirrors routes/articles.py::_card_cut — the card in the markup and the card
    the runtime sync swaps in have to resolve to the same file, or every view
    would replace one with the other.
    """
    stem, dot, ext = rel.rpartition(".")
    if not stem:
        return rel
    # Test the candidate rather than the stem's spelling: "kisan-credit-card"
    # ends in "-card" and is not a card cut, and a stem-based guard silently
    # left that article (and mitti-jaanch-soil-health-card) on the 1200px file.
    cut = f"{stem}-card{dot}{ext}"
    return cut if cut != rel and (FRONTEND / cut).is_file() else rel


def _og_image(a: dict) -> str:
    """og:image — the hero if there is one, else the site banner."""
    hero = _hero(a)
    if hero:
        return f"{SITE}/{hero[0]}"
    return a.get("og_image") or FALLBACK_OG


# ── page rendering ─────────────────────────────────────────────────────────

def render(a: dict) -> str:
    missing = [k for k in REQUIRED_KEYS if k not in a]
    if missing:
        raise SystemExit(f"article_builder: {a.get('slug', '?')} is missing "
                         f"required key(s): {', '.join(missing)}")
    missing = [k for k in REQUIRED_CARD_KEYS if k not in a["card"]]
    if missing:
        raise SystemExit(f"article_builder: {a['slug']} card is missing "
                         f"key(s): {', '.join(missing)}")
    if a["slug"] != a["slug"].lower():
        raise SystemExit(f"article_builder: slug must be lowercase: {a['slug']}")

    lang = a.get("lang", "hi")
    if lang not in LOCALES:
        raise SystemExit(f"article_builder: {a['slug']} has lang={lang!r}, which "
                         f"has no entry in LOCALES (have: {', '.join(LOCALES)}). "
                         f"Add one rather than letting the page declare Hindi.")
    loc = LOCALES[lang]

    shell = _load_shell()
    url = _canonical(a["slug"])
    faqs = a["faqs"]
    hero = _hero(a)
    og_image = _og_image(a)

    if hero:
        path, alt, caption = hero
        figure = (
            '\n  <!-- FEATURED IMAGE -->\n'
            '  <figure class="featured-image">\n'
            f'    <img src="../{path}" alt="{alt}" width="1200" height="675" '
            'loading="eager" fetchpriority="high" decoding="async" />\n'
            + (f'    <figcaption>{caption}</figcaption>\n' if caption else '')
            + '  </figure>\n'
        )
    else:
        figure = ""

    # The visible markup and the schema come from the same list, in the same
    # pass. There is no way to change one without the other.
    faq_markup = "\n".join(
        f'    <div class="faq-item">\n'
        f'      <div class="faq-q"><span class="num">{i}</span>{q}</div>\n'
        f'      <div class="faq-a">{ans}</div>\n'
        f'    </div>'
        for i, (q, ans) in enumerate(faqs, 1))

    faq_schema = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": _plain(q),
                        "acceptedAnswer": {"@type": "Answer", "text": _plain(ans)}}
                       for q, ans in faqs],
    }

    article_schema = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": a["headline"], "alternativeHeadline": a["headline_en"],
        "description": a["schema_desc"], "image": og_image, "url": url,
        "inLanguage": lang,
        "datePublished": a["date"], "dateModified": a.get("date_modified", a["date"]),
        "author": {"@type": "Person", "@id": f"{SITE}/about#kunal-rajput",
                   "name": "Kunal Rajput", "url": f"{SITE}/about"},
        "publisher": {"@type": "Organization", "name": "KrashiMitra", "url": SITE,
                      "logo": {"@type": "ImageObject",
                               "url": f"{SITE}/assets/krashimitra_logo.png"}},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "keywords": a["schema_keywords"], "articleSection": a["section"],
        "wordCount": a["word_count"],
    }

    breadcrumb_schema = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": loc["home"], "item": SITE},
            {"@type": "ListItem", "position": 2, "name": loc["articles"],
             "item": f"{SITE}/articles/"},
            {"@type": "ListItem", "position": 3, "name": a["cat_label"],
             "item": f"{SITE}/articles/?cat={a['cat_query']}"},
            {"@type": "ListItem", "position": 4, "name": a["breadcrumb_leaf"]},
        ],
    }

    badges = "\n      ".join(f'<span class="badge {c}">{t}</span>'
                             for c, t in a["badges"])

    facts = "\n    ".join(
        f'<div class="fact-card{(" " + c) if c else ""}">\n'
        f'      <div class="f-icon">{icon}</div>\n'
        f'      <div class="f-val">{val}</div>\n'
        f'      <div class="f-label">{label}</div>\n'
        f'    </div>'
        for c, icon, val, label in a["quick_facts"])

    chips = "".join(
        f'<a href="{SITE}/bhav/{s}" style="display:inline-block;background:#fff;'
        f'border:1px solid #cfe3cf;border-radius:16px;padding:4px 12px;'
        f'margin:3px 6px 3px 0;text-decoration:none;color:#1b7a3d">{label}</a>'
        for s, label in a["bhav_links"])
    chips += (f'<a href="{SITE}/bhav/" style="display:inline-block;background:#1b7a3d;'
              f'border-radius:16px;padding:4px 12px;margin:3px 6px 3px 0;'
              f'text-decoration:none;color:#fff">{loc["all_prices"]}</a>')

    wa = quote(f"{a['share_title']} | KrashiMitra\n{url}", safe="")

    related = "\n".join(
        f'      <a class="article-card" href="{href}" style="--rc-accent:{accent}">\n'
        f'        <div class="card-thumb">{thumb}</div>\n'
        f'        <div class="card-body">\n'
        f'          <div class="card-tag">{tag}</div>\n'
        f'          <div class="card-title">{title}</div>\n'
        f'        </div>\n'
        f'        <span class="card-arrow">›</span>\n'
        f'      </a>\n'
        for href, accent, thumb, tag, title in a["related"])

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />

  <!-- SEO -->
  <title>{a['title']}</title>
  <link rel="icon" type="image/png" href="{SITE}/assets/krashimitra_logo.png">
  <meta name="description" content="{a['description']}" />
  <meta name="keywords" content="{a['keywords']}" />
  <meta name="author" content="Kunal Rajput — KrashiMitra" />
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1" />
  <link rel="canonical" href="{url}" />
  <link rel="alternate" hreflang="{lang}" href="{url}" />
  <link rel="alternate" hreflang="x-default" href="{url}" />
  <meta name="theme-color" content="#1a4d2e" />

  <!-- Open Graph -->
  <meta property="og:title" content="{a['og_title']}" />
  <meta property="og:description" content="{a['og_desc']}" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="{url}" />
  <meta property="og:image" content="{og_image}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta property="og:locale" content="{lang}_IN" />
  <meta property="og:site_name" content="KrashiMitra" />

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{a['og_title']}" />
  <meta name="twitter:description" content="{a['og_desc']}" />
  <meta name="twitter:image" content="{og_image}" />

  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?{loc['fonts']}&family=Poppins:wght@400;500;600;700&family=DM+Sans:wght@400;500;700&display=swap">

  <!-- Universal page shell (header / drawer / blue bar / footer) -->
  <link rel="stylesheet" href="../km-shell.css">

  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-493H1PDP64"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-493H1PDP64');</script>

  <!-- Structured Data: Article -->
  <script type="application/ld+json">
{_j(article_schema)}
  </script>

  <!-- Structured Data: BreadcrumbList -->
  <script type="application/ld+json">
{_j(breadcrumb_schema)}
  </script>

{shell['style']}

  <!-- Structured Data: FAQPage — generated from the visible .faq-item markup below -->
  <script type="application/ld+json">
{_j(faq_schema)}
  </script>
</head>
<body>

{shell['header']}

<!-- Breadcrumb -->
<div class="breadcrumb">
  <a href="{SITE}">🏠 {loc['home']}</a>
  <span class="sep">›</span>
  <a href="{SITE}/articles/">📰 {loc['articles']}</a>
  <span class="sep">›</span>
  <a href="{SITE}/articles/?cat={a['cat_query']}">{a['cat_label']}</a>
  <span class="sep">›</span>
  <span class="current">{a['breadcrumb_leaf']}</span>
</div>

<!-- ════════════════════════════════════════
     HERO
════════════════════════════════════════ -->
<div class="hero">
  <div class="hero-inner">
    <div class="hero-badges">
      {badges}
    </div>

    <h1>
      {a['h1']}
      <span class="en-title">{a['h1_en']}</span>
    </h1>

    <p class="hero-excerpt">
      {a['hero_excerpt']}
    </p>

    <div class="hero-meta">
      <span>✍️ <a href="/about" style="color:inherit;">Kunal Rajput</a> — KrashiMitra</span>
      <span class="read-time">⏱️ {a['read_time']} {loc['read']}</span>
      <span>📅 {a['date_label']}</span>
      <div class="hero-share">
        <button class="share-btn" onclick="if(navigator.share){{navigator.share({{title:'{a['share_title']}',url:window.location.href}})}}else{{navigator.clipboard.writeText(window.location.href);alert('{loc["copied"]}')}}">
          📤 {loc['share']}
        </button>
        <button class="share-btn" onclick="window.print()">🖨️ {loc['print']}</button>
      </div>
    </div>
  </div>
</div>

<!-- ════════════════════════════════════════
     ARTICLE CONTENT
════════════════════════════════════════ -->
<div class="article-wrapper">
{figure}
  <div class="section-heading"></div>
  <h2>{a['lede_h2']}</h2>

  <!-- QUICK FACTS -->
  <div class="quick-facts">
    {facts}
  </div>

{a['body']}

  <!-- ── AD SLOT : before FAQ ── -->
  <div class="ad-slot responsive" aria-label="{loc['ad']}">
    <div class="ad-slot-label">{loc['ad']}</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="7350859053" data-format="auto"></div>
    </div>
  </div>

  <!-- FAQ -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">❓</span>
      <h2>{loc['faq_h2']}</h2>
    </div>
{faq_markup}
  </section>

  <!-- CTA -->
  <div class="cta-block">
    <div class="cta-icon">🌾</div>
    <h3>{loc['cta_h3']}</h3>
    <p>{loc['cta_p']}</p>
    <a href="{SITE}">{loc['cta_a']}</a>
  </div>

  <!-- ════════════════════════════════════════
       RELEVANT ARTICLES
  ════════════════════════════════════════ -->
  <div class="relevant-articles">
    <div class="section-title">
      <span class="title-icon">📰</span>
      {loc['related_h']}
      <a href="{SITE}/articles/">{loc['all_articles']}</a>
    </div>

    <div class="articles-grid">

{related}
    </div>
  </div>

</div><!-- /article-wrapper -->

{shell['cta']}

<!-- bhav-links: live mandi-price pages + share -->
<section class="bhav-links" style="max-width:860px;margin:28px auto;padding:18px 20px;background:#f0f7f0;border:1px solid #cfe3cf;border-radius:12px;font-family:inherit">
  <h2 style="font-size:1.05rem;margin:0 0 10px;color:#1b5a2d">{loc['bhav_h2']}</h2>
  <p style="margin:0 0 12px;line-height:2">{chips}</p>
  <a href="https://wa.me/?text={wa}" style="display:inline-block;background:#25d366;color:#fff;font-weight:700;padding:9px 16px;border-radius:22px;text-decoration:none">{loc['wa_share']}</a>
</section>
{shell['tail']}"""


# ── site wiring ────────────────────────────────────────────────────────────

def sync_index_card(a: dict) -> str:
    """Insert or refresh this article's card in frontend/articles/index.html.

    Newest first, so a new card goes to the top of #articles-list. Re-running
    the builder replaces the existing card rather than adding a second one.
    """
    c, slug = a["card"], a["slug"]
    hero = _hero(a)
    # The emoji stays in the markup either way — it is the layered fallback the
    # band reveals if the image 404s, not an alternative to having one.
    if hero:
        media = (
            f'      <div class="article-media" style="background:{c["bg"]}">\n'
            f'        <img src="../{_card_cut(hero[0])}" alt="{hero[1] or c["title"]}" '
            f'loading="lazy" decoding="async" onerror="this.closest'
            f"('.article-media').classList.add('noimg');this.remove()\">\n"
            f'        <span class="article-media-emoji">{c["emoji"]}</span>\n'
            f'      </div>\n'
        )
    else:
        media = (
            f'      <div class="article-media noimg" style="background:{c["bg"]}">\n'
            f'        <span class="article-media-emoji">{c["emoji"]}</span>\n'
            f'      </div>\n'
        )
    card = (
        f'    <!-- {c["title"]} -->\n'
        f'    <a class="article-card" href="{slug}" data-cat="{c["cats"]}" '
        f'data-lang="{a.get("lang", "hi")}" data-title="{c["keywords"]}" '
        f'style="--accent:{c["accent"]}">\n'
        f'{media}'
        f'      <div class="article-body">\n'
        f'        <span class="article-tag" style="background:{c["tag_bg"]};'
        f'color:{c["tag_color"]}">{c["tag"]}</span>\n'
        f'        <div class="article-title">{c["title"]}</div>\n'
        f'        <div class="article-footer">\n'
        f'          <div class="article-meta">⏱️ {a["read_time"]} मिनट '
        f'<span class="meta-dot" style="display:inline-block;width:3px;height:3px;'
        f'border-radius:50%;background:currentColor;margin:0 2px;"></span> नया</div>\n'
        f'          <div class="article-views">👁 नया</div>\n'
        f'        </div>\n'
        f'      </div>\n'
        f'    </a>\n'
    )

    doc = INDEX.read_text(encoding="utf-8")
    # Match the canonical extensionless href and the legacy "<slug>.html" one,
    # so a card written before the switch is replaced rather than duplicated.
    existing = re.search(
        rf'[ \t]*<!--[^\n]*-->\n[ \t]*<a class="article-card" '
        rf'href="{re.escape(slug)}(?:\.html)?".*?</a>\n',
        doc, re.S)
    if existing:
        doc = doc[:existing.start()] + card + doc[existing.end():]
        action = "updated"
    else:
        anchor = '<div class="articles-list" id="articles-list">\n'
        i = doc.index(anchor) + len(anchor)
        doc = doc[:i] + "\n" + card + doc[i:]
        action = "inserted"
    doc = _sync_index_count(doc)
    INDEX.write_text(doc, encoding="utf-8")
    return action


def _sync_index_count(doc: str) -> str:
    """Keep the "N+ विशेषज्ञ कृषि लेख" claim in the index metadata truthful.

    It was hand-written, so it still said 31+ at 59 articles. Rounding down to
    the nearest 5 keeps the claim true for the next few articles instead of
    going stale the moment one is added.
    """
    n = sum(1 for f in ARTICLES.glob("*.html") if f.name not in {"index.html"})
    claim = f"{n // 5 * 5}+"
    return re.sub(r"\d+\+(?= विशेषज्ञ कृषि लेख)", claim, doc)


def sync_redirects() -> list[str]:
    """Rebuild the article 301 block in _redirects from the files on disk.

    Netlify reads _redirects as a static file, so unlike sitemap.xml this cannot
    be generated per request — but it uses sitemap.py's slug rule (stem.lower()),
    so the two cannot disagree. No wildcards: Netlify placeholders match whole
    path segments only, so /articles/:slug.html emits a literal ":slug".
    """
    head = "# Canonical article URLs: 301 old .html forms to extensionless"
    lines = REDIRECTS.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith(head))
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "")

    block = [lines[start], lines[start + 1],
             "/articles/index.html   /articles/   301!"]
    # plain-string sort: WindowsPath compares case-folded, which would reshuffle
    # the whole block against the committed ASCII order.
    for f in sorted(ARTICLES.glob("*.html"), key=lambda p: p.name):
        if f.name == "index.html":
            continue
        block.append(f"/articles/{f.name}   /articles/{f.stem.lower()}   301!")

    before = {l for l in lines[start:end] if l.startswith("/articles/")}
    after = {l for l in block if l.startswith("/articles/")}
    if before != after:
        REDIRECTS.write_text("\n".join(lines[:start] + block + lines[end:]),
                             encoding="utf-8")
    return sorted(after - before)


# ── validation ─────────────────────────────────────────────────────────────

def _visible(doc: str) -> str:
    t = re.sub(r"<script\b.*?</script>", " ", doc, flags=re.S | re.I)
    t = re.sub(r"<style\b.*?</style>", " ", t, flags=re.S | re.I)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", t)))


def validate(path: Path) -> list[str]:
    """Every rule this site has learned the hard way, asserted on one page."""
    doc = path.read_text(encoding="utf-8")
    vis = _visible(doc)
    bad: list[str] = []

    def check(cond, msg):
        if not cond:
            bad.append(msg)

    check(doc.count("<h1>") == 1, f"expected 1 <h1>, got {doc.count('<h1>')}")
    check(path.stem == path.stem.lower(), "filename not lowercase — sitemap slug would differ")

    want = _canonical(path.stem)
    canon = re.search(r'<link rel="canonical" href="([^"]+)"', doc)
    check(canon and canon.group(1) == want, "canonical != sitemap slug URL")
    ogu = re.search(r'<meta property="og:url" content="([^"]+)"', doc)
    check(ogu and ogu.group(1) == want, "og:url != canonical")
    mid = re.search(r'"@id": "(https://krashimitra\.in/articles/[^"]+)"', doc)
    check(mid and mid.group(1) == want, "mainEntityOfPage @id != canonical")

    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', doc, re.S)
    check(len(blocks) == 3, f"expected 3 JSON-LD blocks, got {len(blocks)}")
    parsed = []
    for i, b in enumerate(blocks):
        try:
            parsed.append(json.loads(b))
        except Exception as e:
            bad.append(f"JSON-LD block {i} invalid: {e}")

    # FAQ schema must mirror the visible markup — Google suppresses rich results
    # for mismatched FAQPage markup and can issue a manual action.
    faq = next((p for p in parsed if p.get("@type") == "FAQPage"), None)
    check(faq is not None, "no FAQPage schema")
    if faq:
        norm = lambda s: re.sub(r"\s+", " ", htmllib.unescape(
            re.sub(r"<[^>]+>", "", s))).strip()
        vq = [norm(m) for m in re.findall(
            r'<div class="faq-q"><span class="num">\d+</span>(.*?)</div>', doc, re.S)]
        va = [norm(m) for m in re.findall(r'<div class="faq-a">(.*?)</div>', doc, re.S)]
        check(vq == [e["name"] for e in faq["mainEntity"]],
              "FAQ questions differ between schema and visible markup")
        check(va == [e["acceptedAnswer"]["text"] for e in faq["mainEntity"]],
              "FAQ answers differ between schema and visible markup")
        squash = lambda s: re.sub(r"\s+", "", s)
        vis_sq = squash(vis)
        for e in faq["mainEntity"]:
            check(squash(e["acceptedAnswer"]["text"]) in vis_sq,
                  f"schema answer not visible on page: {e['name'][:40]}")
        check(len(faq["mainEntity"]) >= 5,
              f"only {len(faq['mainEntity'])} FAQs (want 6-8)")

    # A missing static file is served as the 200-HTML fallback, never a 404 —
    # broken asset paths fail silently in production, so assert on disk.
    og = re.search(r'<meta property="og:image" content="([^"]+)"', doc)
    if og:
        rel = og.group(1).replace(f"{SITE}/", "")
        check((FRONTEND / rel).is_file(), f"og:image not on disk: {rel}")
        # The generic banner as og:image means no picture was ever sourced. It
        # went unnoticed on 44 articles at once, so it fails the build now.
        check(og.group(1) != FALLBACK_OG,
              "og:image is the generic site banner — set hero_image")
    check('class="featured-image"' in doc, "no hero <figure> on the page")
    for m in re.findall(r'(?:src|href)="\.\./([^"?#]+)"', doc):
        check((FRONTEND / m).is_file(), f"missing relative asset ../{m}")
    for m in set(re.findall(
            r'href="(?:https://krashimitra\.in)?/articles/([a-z0-9_\-]+)"', doc)):
        check(any(p.stem.lower() == m for p in ARTICLES.glob("*.html")),
              f"internal link has no file: /articles/{m}")

    # An unclosed div inside the desktop-only .top-utility-bar swallows the whole
    # page on mobile while desktop still looks fine.
    for t in ("section", "table", "div"):
        o, c = len(re.findall(rf"<{t}[\s>]", doc)), len(re.findall(rf"</{t}>", doc))
        check(o == c, f"<{t}> unbalanced: {o} open vs {c} close")

    for needle in ("km-shell.css", "drawer-menu.js", "bottomnav.js",
                   "header-scroll.js", "km-ad-slot", 'class="header-wrapper"',
                   "km-footer"):
        check(needle in doc, f"missing shell piece: {needle}")

    t = re.search(r"<title>(.*?)</title>", doc, re.S)
    d = re.search(r'<meta name="description" content="([^"]+)"', doc)
    # Google truncates titles ~60 chars and descriptions ~160 — longer copy
    # shows chopped in the SERP and kills CTR.
    check(t and 30 < len(t.group(1)) <= 68, "title length outside 30-68")
    check(d and 70 < len(d.group(1)) <= 162, "description length outside 70-162")

    check(len(vis.split()) >= 1200, f"only {len(vis.split())} words (want 2000+)")
    check("{{" not in doc, "unrendered template placeholder")
    return bad


# ── CLI ────────────────────────────────────────────────────────────────────

def _load_content(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "ARTICLE"):
        raise SystemExit(f"article_builder: {path.name} defines no ARTICLE dict")
    return mod.ARTICLE


def build_one(content_path: Path, write: bool = True) -> tuple[Path, list[str]]:
    a = _load_content(content_path)
    out = ARTICLES / f"{a['slug']}.html"
    html_text = render(a)
    if write:
        out.write_text(html_text, encoding="utf-8")
        card = sync_index_card(a)
        added = sync_redirects()
        print(f"  page      {out.relative_to(ROOT)}  "
              f"({len(html_text.splitlines())} lines)")
        print(f"  index     card {card}")
        for l in added:
            print(f"  redirect  + {l}")
    return out, validate(out) if out.is_file() else ["not built"]


def main() -> int:
    p = argparse.ArgumentParser(description="Build a KrashiMitra article from a content module.")
    p.add_argument("content", nargs="*", type=Path,
                   help="tools/articles/<name>.py (omit with --all)")
    p.add_argument("--all", action="store_true",
                   help="rebuild every content module in tools/articles/")
    p.add_argument("--check", action="store_true",
                   help="validate the built pages, write nothing")
    args = p.parse_args()

    if args.all:
        targets = sorted(f for f in CONTENT_DIR.glob("*.py")
                         if not f.name.startswith("_"))
    else:
        targets = args.content
    if not targets:
        p.error("give a content module, or --all")

    failed = False
    for t in targets:
        if not t.is_file():
            print(f"✗ {t}: no such file")
            failed = True
            continue
        print(f"{t.name}")
        _, problems = build_one(t, write=not args.check)
        if problems:
            failed = True
            print(f"  ✗ {len(problems)} problem(s):")
            for x in problems:
                print(f"      - {x}")
        else:
            print("  ✓ all checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
