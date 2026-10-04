# -*- coding: utf-8 -*-
# আমন ধান কাটা, শুকানো ও বিক্রি — Bengali (lang "bn"), October 2026 round.
# Harvest timing, drying, storage, straw and selling. Procurement terms are a
# referral to the official department; the page says it is a private site.

SITE = "https://krashimitra.in"

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>ভূমিকা</h2>
    </div>
    <p>
      অগ্রহায়ণ মানেই বাংলার মাঠে সোনালি <strong>আমন ধান</strong> — বর্ধমান, বীরভূম, হুগলি, বাঁকুড়া,
      মেদিনীপুর, নদিয়া থেকে উত্তরবঙ্গ পর্যন্ত। সারা বছরের সবচেয়ে বড় ফসল এটাই, আর নবান্নের উৎসবও
      এই ধানকে ঘিরে।
    </p>
    <p>
      কিন্তু মাঠে ভালো ফলন হলেও অনেক চাষি শেষ ধাপে টাকা হারান। দেরিতে কাটায় দানা ঝরে যায়, ভেজা ধান
      গোলায় তুলে ছত্রাক লাগে, আর ক্রয়কেন্দ্রে আর্দ্রতা বেশি বলে ধান ফিরিয়ে দেওয়া হয় বা দাম কাটা যায়।
      এই প্রবন্ধে <strong>কাটা, শুকানো, রাখা আর বিক্রির</strong> প্রতিটি ধাপ সহজ করে বলা হল।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 1 ── -->
  <div class="ad-slot leaderboard" aria-label="বিজ্ঞাপন">
    <div class="ad-slot-label">বিজ্ঞাপন</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="3367685932" data-format="auto"></div>
    </div>
  </div>

  <!-- WHEN TO HARVEST -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔍</span>
      <h2>কখন কাটবেন — চেনার উপায়</h2>
    </div>
    <p>
      শিষের <strong>বেশিরভাগ (প্রায় চার ভাগের তিন ভাগের বেশি) দানা সোনালি</strong> হয়ে এলে আর দানা দাঁতে
      কাটলে শক্ত লাগলে ধান কাটার উপযুক্ত। শিষের গোড়ার দিকে দু-চারটে দানা একটু সবুজ থাকলেও চলে।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>অবস্থা</th><th>✅ ঠিক সময়</th><th>❌ আগে বা দেরিতে</th></tr>
      </thead>
      <tbody>
        <tr><td>দানার রং</td><td class="healthy">বেশিরভাগ সোনালি</td><td class="diseased">অনেক সবুজ, বা সব শুকিয়ে ঝরছে</td></tr>
        <tr><td>দানা</td><td class="healthy">দাঁতে কাটলে শক্ত</td><td class="diseased">দুধ-দুধ নরম, বা ভঙ্গুর</td></tr>
        <tr><td>ফল</td><td class="healthy">পুরো ওজন, কম ভাঙা চাল</td><td class="diseased">আগে কাটলে চিটা; দেরিতে কাটলে ঝরা আর ভাঙা চাল</td></tr>
      </tbody>
    </table>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        দেরিতে কাটা ধান চালকলে ভাঙে বেশি। চালকল মালিকরা আস্ত চালের ভাগ দেখে দাম দেন, তাই সময়ে
        কাটা মানে ভালো দাম।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- DRYING -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">☀️</span>
      <h2>শুকানো — আর্দ্রতাই আসল খেলা</h2>
    </div>
    <p>
      কাটার সময় ধানে অনেক জল থাকে। সরকারি ক্রয়ের মানদণ্ডে ধানের আর্দ্রতার সর্বোচ্চ সীমা সাধারণত
      <strong>১৭ শতাংশ</strong> ধরা হয়; গোলায় অনেক দিন রাখতে চাইলে আরও শুকনো হওয়া দরকার। নিয়ম বদলাতে
      পারে, তাই বিক্রির আগে ক্রয়কেন্দ্রে যাচাই করুন।
    </p>
    <ul>
      <li><strong>ত্রিপলে শুকান:</strong> সরাসরি মাটিতে বা রাস্তায় শুকালে মাটি, পাথর মেশে আর দাম কমে।</li>
      <li><strong>পাতলা স্তর, বারবার উল্টানো:</strong> মোটা স্তরে নিচের ধান ভেজা থেকে যায়।</li>
      <li><strong>সন্ধ্যায় ঢেকে দিন:</strong> রাতের শিশির আবার ধান ভিজিয়ে দেয়।</li>
      <li><strong>ঝাড়াই:</strong> চিটা, খড়ের টুকরো আর ধুলো ঝেড়ে পরিষ্কার করুন — পরিষ্কার ধানই ভালো দাম পায়।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 2 ── -->
  <div class="ad-slot responsive" aria-label="বিজ্ঞাপন">
    <div class="ad-slot-label">বিজ্ঞাপন</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="4489195916" data-format="auto"></div>
    </div>
  </div>

  <!-- STORAGE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏚️</span>
      <h2>গোলা আর বস্তায় রাখা</h2>
    </div>
    <ul>
      <li><strong>পুরো শুকনো ধান:</strong> দাঁতে কাটলে "কট" শব্দ হলে বোঝা যায় ধান শুকিয়েছে।</li>
      <li><strong>পরিষ্কার গোলা:</strong> নতুন ধান তোলার আগে পুরোনো দানা, ধুলো আর পোকা পরিষ্কার করুন।</li>
      <li><strong>মাটি থেকে উঁচুতে:</strong> বস্তা কাঠের পাটাতনে রাখুন, দেয়াল থেকে একটু দূরে।</li>
      <li><strong>ইঁদুর:</strong> গোলার চারপাশ পরিষ্কার রাখুন, ফাঁকফোকর বন্ধ করুন।</li>
      <li><strong>মাসে একবার দেখা:</strong> গরম ভাব, গন্ধ বা পোকা দেখলে আবার রোদে দিন।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- STRAW -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🌾</span>
      <h2>খড় পোড়াবেন না — এটাও টাকা</h2>
    </div>
    <p>
      কম্বাইন হারভেস্টারে কাটলে মাঠে লম্বা নাড়া থেকে যায়, আর অনেকে তাড়াতাড়ি পরের চাষের জন্য তাতে
      আগুন দেন। এতে মাটির জৈব পদার্থ আর উপকারী জীবাণু পুড়ে যায়, ধোঁয়ায় মানুষের কষ্ট হয়। খড় গবাদি
      পশুর খাবার, মাশরুম চাষ, ঘর ছাওয়া আর জৈব সারের কাজে লাগে — অনেক এলাকায় খড়ের ভালো বাজারও আছে।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- SELLING -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💰</span>
      <h2>বিক্রি — সরকারি ক্রয় না খোলা বাজার</h2>
    </div>
    <ul>
      <li><strong>সরকারি ন্যূনতম সহায়ক মূল্যে বিক্রি:</strong> রাজ্য সরকার ক্রয়কেন্দ্রের মাধ্যমে ধান কেনে। নাম নথিভুক্তি, তারিখ, আর্দ্রতা আর কাগজপত্রের নিয়ম খাদ্য ও সরবরাহ দপ্তরের সরকারি ওয়েবসাইট বা ব্লক অফিসে জেনে নিন। KrashiMitra একটি বেসরকারি ওয়েবসাইট — আমরা কোনো আবেদন বা টাকা নিই না।</li>
      <li><strong>চালকল বা ব্যবসায়ী:</strong> নগদ টাকা দ্রুত মেলে, কিন্তু দাম আর ওজন দুটোই যাচাই করুন।</li>
      <li><strong>ভাগে ভাগে বিক্রি:</strong> সব ধান একদিনে না বেচে কিছুটা গোলায় রেখে বাজারদর দেখে বিক্রি করা যায়।</li>
      <li><strong>বীজের ধান আলাদা:</strong> সবচেয়ে ভালো জমির পরিষ্কার ধান পরের বছরের বীজের জন্য আলাদা রাখুন।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- MISTAKES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚫</span>
      <h2>এই ভুলগুলো কখনও করবেন না</h2>
    </div>
    <ul>
      <li><strong>দেরিতে কাটা</strong> — দানা ঝরে, চাল ভাঙে।</li>
      <li><strong>রাস্তায় ধান শুকানো</strong> — ময়লা মেশে, দুর্ঘটনার ঝুঁকিও।</li>
      <li><strong>ভেজা ধান গোলায় তোলা</strong> — ছত্রাক, গন্ধ আর পোকা।</li>
      <li><strong>নাড়ায় আগুন</strong> — মাটির ক্ষতি, ধোঁয়া আর আইনি ঝামেলা।</li>
      <li><strong>নিয়ম না জেনে ক্রয়কেন্দ্রে যাওয়া</strong> — ধান ফেরত আসতে পারে।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CALENDAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>কাটা থেকে বিক্রি — ক্যালেন্ডার</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>সময়</th><th>জরুরি কাজ</th></tr></thead>
      <tbody>
        <tr><td>অক্টোবর</td><td>ত্রিপল, বস্তা, গোলা পরিষ্কার; ক্রয়কেন্দ্রের নিয়ম জেনে নেওয়া</td></tr>
        <tr><td>নভেম্বর-ডিসেম্বর</td><td>সময়ে কাটা, ত্রিপলে শুকানো, ঝাড়াই</td></tr>
        <tr><td>ডিসেম্বর</td><td>খড় গুছিয়ে রাখা বা বিক্রি; পরের ফসলের জমি তৈরি</td></tr>
        <tr><td>ডিসেম্বর-ফেব্রুয়ারি</td><td>দরদাম দেখে ভাগে ভাগে বিক্রি, গোলা নিয়মিত দেখা</td></tr>
      </tbody>
    </table>
  </section>

  <hr class="section-divider" />

  <!-- CONCLUSION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✅</span>
      <h2>উপসংহার</h2>
    </div>
    <p>
      আমনের লাভ শেষ মাসে ঠিক হয়। তিনটি কথা: <strong>সময়ে কাটা</strong>, <strong>ত্রিপলে ভালো করে শুকানো</strong>
      আর <strong>নিয়ম জেনে, দর দেখে বিক্রি</strong>।
    </p>
    <p><strong>মাঠের সোনা গোলায় সোনা থাকুক — ভেজা হয়ে মাটি না হোক।</strong></p>
  </section>
"""

FAQS = [
    ("আমন ধান কখন কাটতে হয়?",
     "শিষের <strong>বেশিরভাগ দানা সোনালি</strong> হয়ে এলে আর দানা দাঁতে কাটলে শক্ত লাগলে আমন ধান কাটার সময়। পশ্চিমবঙ্গে এটা সাধারণত নভেম্বর-ডিসেম্বর। দেরিতে কাটলে দানা ঝরে আর চাল ভাঙে।"),
    ("ধান বিক্রির জন্য আর্দ্রতা কত হতে হবে?",
     "সরকারি ক্রয়ের মানদণ্ডে ধানের আর্দ্রতার সর্বোচ্চ সীমা সাধারণত <strong>১৭ শতাংশ</strong> ধরা হয়। নিয়ম বদলাতে পারে, তাই বিক্রির আগে ক্রয়কেন্দ্রে যাচাই করুন।"),
    ("aman paddy harvest — ধান কীভাবে শুকাব?",
     "<strong>ত্রিপলে পাতলা স্তরে</strong> ছড়িয়ে বারবার উল্টে দিন আর সন্ধ্যায় ঢেকে রাখুন। রাস্তায় বা সরাসরি মাটিতে শুকালে ময়লা মেশে আর দাম কমে।"),
    ("সহায়ক মূল্যে ধান বিক্রি করতে কী লাগে?",
     "রাজ্য সরকারের ক্রয়কেন্দ্রে বিক্রির জন্য <strong>আগে নাম নথিভুক্তি</strong> করতে হয় আর কিছু কাগজপত্র লাগে। সঠিক নিয়ম খাদ্য ও সরবরাহ দপ্তরের সরকারি ওয়েবসাইট বা ব্লক অফিস থেকে জেনে নিন।"),
    ("ধানের নাড়া পোড়ানো কেন খারাপ?",
     "নাড়া পোড়ালে <strong>মাটির জৈব পদার্থ আর উপকারী জীবাণু নষ্ট হয়</strong>, ধোঁয়ায় মানুষের কষ্ট হয়। খড় পশুখাদ্য, মাশরুম চাষ আর জৈব সারের কাজে লাগে, অনেক জায়গায় বিক্রিও হয়।"),
    ("গোলায় ধান কীভাবে ভালো থাকবে?",
     "<strong>পুরো শুকনো, পরিষ্কার ধান</strong> পরিষ্কার গোলায় বা কাঠের পাটাতনে রাখা বস্তায় তুলুন। মাসে একবার দেখুন — গরম ভাব, গন্ধ বা পোকা দেখলে আবার রোদে দিন।"),
]

ARTICLE = {
    "slug": "aman-dhan-kata-paschimbanga",
    "date": "2026-10-05",
    "date_label": "অক্টোবর ২০২৬",
    "read_time": 8,
    "word_count": 1600,
    "lang": "bn",

    "section": "ধান চাষ",
    "cat_label": "ধান চাষ",
    "cat_query": "anaaj",
    "breadcrumb_leaf": "আমন ধান কাটা",

    "title": "আমন ধান কখন কাটবেন? শুকানো, রাখা ও বিক্রি (২০২৬)",
    "description": "আমন ধান কাটার সঠিক সময়, ত্রিপলে শুকানো, ১৭% আর্দ্রতার নিয়ম, গোলায় রাখা, খড় না পোড়ানো আর সহায়ক মূল্যে বা বাজারে বিক্রির পুরো গাইড।",
    "keywords": "আমন ধান, আমন ধান কাটা, ধান শুকানো, ধানের আর্দ্রতা, aman paddy, aman dhan, ধান বিক্রি, সহায়ক মূল্য ধান, গোলা, পশ্চিমবঙ্গ ধান",

    "og_title": "আমন ধান — কাটা থেকে বিক্রি | KrashiMitra.in",
    "og_desc": "সময়ে কাটা, ভালো করে শুকানো, নিয়ম জেনে বিক্রি — আমনের লাভ শেষ মাসে ঠিক হয়।",

    "hero_image": ("images/articles/body-paddy-field.webp",
                   "পাকা ধানের ক্ষেত",
                   "পাকা ধানের ক্ষেত। শিষের বেশিরভাগ দানা সোনালি হলে কাটার সময়।"),

    "headline": "আমন ধান কাটা, শুকানো, গোলায় রাখা ও বিক্রি",
    "headline_en": "Aman Paddy Harvest in West Bengal — Timing, Drying, Storage and Selling",
    "schema_desc": "আমন ধান কাটার সময় চেনা, ত্রিপলে শুকানো, আর্দ্রতা, গোলায় রাখা, খড়ের ব্যবহার আর সরকারি ক্রয় বা বাজারে বিক্রি।",
    "schema_keywords": ["আমন ধান", "aman paddy", "ধান শুকানো", "ধানের আর্দ্রতা", "ধান বিক্রি"],

    "h1": "আমন ধান — কাটা থেকে বিক্রি",
    "h1_en": "Aman Paddy — Harvest to Sale, West Bengal",
    "share_title": "আমন ধান কাটা, শুকানো আর বিক্রির পুরো গাইড",
    "hero_excerpt": "মাঠে ভালো ফলন হলেও অনেক চাষি শেষ ধাপে টাকা হারান — দেরিতে কাটা, ভেজা ধান আর ক্রয়কেন্দ্রে আর্দ্রতার জন্য ফেরত।",
    "lede_h2": "আমন ধান — এক নজরে",

    "badges": [("badge-season", "🗓️ নভেম্বর-ডিসেম্বর"),
               ("badge-location", "📍 পশ্চিমবঙ্গ"),
               ("badge-disease", "💧 আর্দ্রতা")],

    "quick_facts": [("", "🌾", "সোনালি দানা", "কাটার খুঁটি"),
                    ("warn", "💧", "১৭%", "ক্রয়ে আর্দ্রতার সাধারণ সীমা"),
                    ("danger", "🔥", "নাড়া পোড়াবেন না", "খড়ও টাকা")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-common", "ধানের দর"), ("potato", "আলুর দর"),
                   ("mustard", "সরষের দর")],

    "card": {
        "emoji": "🌾",
        "bg": "#f1f8e9",
        "accent": "#558b2f",
        "tag": "আমন ধান · বাংলা",
        "tag_bg": "#f1f8e9",
        "tag_color": "#558b2f",
        "title": "আমন ধান কাটা, শুকানো, রাখা ও বিক্রি",
        "cats": "anaaj",
        "keywords": "আমন ধান aman dhan paddy কাটা শুকানো আর্দ্রতা বিক্রি bengali",
    },

    "related": [
        (f"{SITE}/articles/aloo-chash-paschimbanga", "#a16207", "🥔", "আলু · বাংলা",
         "আলু চাষ — জাত, বীজ আলু ও নাবি ধসা"),
        (f"{SITE}/articles/sorshe-chash-paschimbanga", "#ca8a04", "🌼", "সরষে · বাংলা",
         "সরষে চাষ — পয়রা চাষ, জাব পোকা ও মৌমাছি"),
        (f"{SITE}/articles/dhan-nami-mandi-rejection", "#0369a1", "💧", "ধান · আর্দ্রতা",
         "धान में नमी — मंडी में रिजेक्शन से कैसे बचें"),
        (f"{SITE}/articles/parali-prabandhan", "#b45309", "🔥", "নাড়া · ব্যবস্থাপনা",
         "पराली प्रबंधन — जलाने के बजाय क्या करें"),
        (f"{SITE}/bhav/paddy-common", "#1b7a3d", "💰", "বাজারদর · আজ",
         "ধানের আজকের বাজারদর — LIVE"),
        (f"{SITE}/chat", "#2e7d32", "🤖", "AI · সাহায্য",
         "ফসলের ছবি পাঠান — AI দিয়ে সঙ্গে সঙ্গে চিনুন"),
    ],
}
