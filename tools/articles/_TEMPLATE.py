# -*- coding: utf-8 -*-
# ============================================================
# KrashiMitra article — CONTENT MODULE TEMPLATE
#
# Copy this file to tools/articles/<your_slug>.py, fill it in, then run:
#     python tools/article_builder.py tools/articles/<your_slug>.py
#
# The builder produces the page, the /articles/ card and the _redirects rule,
# then validates the result. You never write the page shell, the CSS or the
# JSON-LD — those are derived. Write the CONTENT.
#
# Files starting with "_" are skipped by --all, so this template never builds.
#
# Read tools/ARTICLE-TEMPLATE.md first — it has the editorial rules (what makes
# a good title, how to pick a topic, what must be true of every claim).
# ============================================================

SITE = "https://krashimitra.in"

# ── BODY ────────────────────────────────────────────────────────────────────
# Raw HTML for everything between the quick-facts strip and the FAQ.
# r""" ... """ so backslashes and quotes are safe.
#
# The rhythm that works, in order (drop what does not apply, keep the order):
#   भूमिका → यह क्या है → पहचान → जीवन चक्र / यह कैसे काम करता है →
#   नुकसान (comparison table) → निगरानी / पात्रता → रोकथाम (free measures) →
#   जैविक-देसी उपाय → रासायनिक / प्रक्रिया (dose or document table) →
#   ये गलतियाँ न करें → कैलेंडर तालिका → निष्कर्ष
#
# Every section is:
#   <section class="article-section">
#     <div class="section-heading"><span class="s-icon">EMOJI</span><h2>…</h2></div>
#     …paragraphs / <ul> / <ol> / table / tip-box…
#   </section>
#   <hr class="section-divider" />
#
# Building blocks available (defined in the shared CSS — do not invent classes):
#   <div class="tip-box info">      + <span class="tip-icon">🌱</span> + .tip-content
#   <div class="tip-box tip">       yellow — a practical shortcut
#   <div class="tip-box warning">   red   — a costly mistake or a caveat
#   <table class="article-table">   <thead><tr><th>…  and  td.healthy / td.diseased
#   <ul> / <ol>                     lead each <li> with a <strong>label:</strong>
#
# Ad slots: put ONE after भूमिका (leaderboard) and ONE around the middle
# (responsive). The builder adds the third before the FAQ. Never above the fold.

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>भूमिका</h2>
    </div>
    <p>
      TODO — Open on the symptom or situation the farmer is actually searching,
      in their words. Name the thing in <strong>bold</strong> in the first
      sentence. State the stake (how much is lost) early.
    </p>
    <p>
      TODO — Second paragraph: the one misconception that costs money, and a
      one-line promise of what this article gives.
    </p>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 1 ── -->
  <div class="ad-slot leaderboard" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="3367685932" data-format="auto"></div>
    </div>
  </div>

  <!-- WHAT IS IT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔍</span>
      <h2>TODO — यह क्या है?</h2>
    </div>
    <p>TODO</p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">TODO — the fact that reframes the problem.</div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- COMPARISON TABLE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📊</span>
      <h2>TODO — नुकसान / तुलना</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>पहचान बिंदु</th><th>✅ स्वस्थ</th><th>❌ ग्रस्त</th></tr>
      </thead>
      <tbody>
        <tr><td>TODO</td><td class="healthy">TODO</td><td class="diseased">TODO</td></tr>
      </tbody>
    </table>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 2 ── -->
  <div class="ad-slot responsive" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="5312478291" data-format="auto"></div>
    </div>
  </div>

  <!-- FREE MEASURES FIRST, PAID MEASURES SECOND -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🛡️</span>
      <h2>TODO — बिना पैसे खर्च किए रोकथाम</h2>
    </div>
    <ul>
      <li><strong>TODO:</strong> TODO</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- DOSES / DOCUMENTS — always with the caveat box -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧪</span>
      <h2>TODO — दवा और सही मात्रा</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>दवा (तकनीकी नाम)</th><th>मात्रा / लीटर पानी</th><th>कब उपयुक्त</th></tr>
      </thead>
      <tbody>
        <tr><td>TODO</td><td>TODO</td><td>TODO</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        TODO — required whenever the article gives doses, rates or money:
        check the CIB&amp;RC label / confirm with the local KVK, बैंक शाखा or
        कृषि विभाग, because state-level advice differs.
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- MISTAKES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚫</span>
      <h2>ये गलतियाँ कभी न करें</h2>
    </div>
    <ul>
      <li><strong>TODO</strong> — TODO</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CALENDAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>TODO — कब क्या करें</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>समय</th><th>ज़रूरी काम</th></tr></thead>
      <tbody>
        <tr><td>TODO</td><td>TODO</td></tr>
      </tbody>
    </table>
  </section>

  <hr class="section-divider" />

  <!-- CONCLUSION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✅</span>
      <h2>निष्कर्ष</h2>
    </div>
    <p>TODO — three things to remember, each in <strong>bold</strong>.</p>
    <p><strong>TODO — one memorable closing line.</strong></p>
  </section>
"""

# ── FAQ ─────────────────────────────────────────────────────────────────────
# 6-8 pairs. These become BOTH the visible FAQ and the FAQPage JSON-LD, from
# this one list — so they can never drift apart.
#
# Write the question exactly as a farmer types it into Google. Put the number
# in the answer's FIRST sentence (that is what gets pulled into a snippet).
# Inline <strong> is fine; block tags are not.
FAQS = [
    ("TODO — सवाल जैसा किसान गूगल पर लिखता है?",
     "TODO — पहला वाक्य ही जवाब दे, संख्या के साथ। फिर 1-2 वाक्य विस्तार।"),
]

# ── METADATA + WIRING ───────────────────────────────────────────────────────
ARTICLE = {
    # slug MUST be lowercase — sitemap.py serves every article at stem.lower()
    # and the builder refuses anything else.
    "slug": "todo-my-article-slug",
    "date": "2026-01-01",            # YYYY-MM-DD, publish date
    "date_label": "जनवरी 2026",       # shown in the hero
    "read_time": 8,                   # minutes
    "word_count": 2500,               # roughly; goes into schema
    "lang": "hi",                     # card language filter

    # Category. cat_query must be a real filter chip in articles/index.html:
    # khad · keet · mausam · ganna · sabji · fruit · anaaj · jankari · karnataka
    "section": "TODO",                # schema articleSection, e.g. "फसल कीट"
    "cat_label": "TODO",              # breadcrumb label, e.g. "फसल कीट"
    "cat_query": "keet",
    "breadcrumb_leaf": "TODO",        # short — the page itself

    # TITLE: put the searcher's literal question in it, and the numeric answer
    # in the description. Position 6-7 with a vague title yields ~1% CTR here.
    # NO "| KrashiMitra" suffix — Google shows the site name separately, and
    # the brand chars push the keywords past the ~60-char SERP truncation.
    "title": "TODO — प्रश्न + (साल)",                          # 30-68 chars
    "description": "TODO — जवाब की संख्या पहले वाक्य में।",     # 70-162 chars
    "keywords": "TODO, comma separated, हिंदी + romanised + English variants",

    "og_title": "TODO | KrashiMitra.in",
    "og_desc": "TODO — one line, benefit-led.",
    # Use a real per-article image under frontend/images/ if you have one and
    # have committed it; og-banner.jpg is the fallback. The builder asserts the
    # file exists — a missing static is served as 200-HTML, never a 404.
    "og_image": "https://krashimitra.in/images/og-banner.jpg",

    "headline": "TODO",               # schema headline (no site suffix)
    "headline_en": "TODO — English equivalent, helps entity matching",
    "schema_desc": "TODO",
    "schema_keywords": ["TODO", "TODO"],

    "h1": "TODO",                     # visible H1 — keep short
    "h1_en": "TODO — English subtitle under the H1 (escape &amp;)",
    "share_title": "TODO — used by the share button and the WhatsApp link",
    "hero_excerpt": "TODO — 2 sentences: the symptom, and the stake.",
    "lede_h2": "TODO — the H2 above the quick-facts strip",

    # Three hero badges: (css class, text).
    # classes: badge-disease (red) · badge-season (amber) · badge-location (green)
    "badges": [("badge-disease", "🐛 TODO"),
               ("badge-season", "🗓️ TODO"),
               ("badge-location", "📍 TODO")],

    # Three quick facts: (variant, emoji, big value, label).
    # variant: "danger" (red) · "warn" (amber) · "" (green)
    "quick_facts": [("danger", "📉", "TODO", "TODO"),
                    ("warn", "🎯", "TODO", "TODO"),
                    ("", "🛡️", "TODO", "TODO")],

    "body": BODY,
    "faqs": FAQS,

    # Live mandi-price chips: (bhav slug, label). VERIFY each slug resolves —
    # /bhav/paddy is a 404 while /bhav/paddy-common is not:
    #   curl -o /dev/null -w "%{http_code}" https://krashimitra.in/bhav/<slug>
    "bhav_links": [("wheat", "गेहूं का भाव")],

    # The /articles/ index card.
    "card": {
        "emoji": "🌾",
        "bg": "#fff9e6",          # media tile background
        "accent": "#ca8a04",      # card accent bar
        "tag": "TODO",            # short pill, e.g. "मक्का कीट"
        "tag_bg": "#fff4e0",
        "tag_color": "#ca8a04",
        "title": "TODO — card title, can differ from the H1",
        "cats": "keet",           # space-separated; must include a real chip id
        "keywords": "TODO — extra search terms for the on-page article search",
    },

    # 5-6 related cards: (href, accent, emoji, tag, title).
    # Mix: sibling articles + one /bhav price page + /chat. Point at real files —
    # the builder checks every /articles/ link resolves.
    "related": [
        (f"{SITE}/articles/todo-sibling", "#ca8a04", "🌽", "TODO · TODO", "TODO"),
        (f"{SITE}/bhav/wheat", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "गेहूं का आज का मंडी भाव — राज्यवार LIVE रेट"),
        (f"{SITE}/chat", "#2e7d32", "🤖", "AI · सहायता",
         "फसल की फोटो भेजें — AI से तुरंत पहचान व इलाज"),
    ],
}
