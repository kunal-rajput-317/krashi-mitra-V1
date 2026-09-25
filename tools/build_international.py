# ============================================================
# KrashiMitra — /international country pages, built from one template
#
# WHY THIS EXISTS — WHAT THE OLD PAGES GOT WRONG.
# Until the 2026-09-10 rewrite /us, /uk, /np, /bd, /id, /ng and /lk were
# seven hand-written 34-77KB HTML files, each carrying its own copy of the
# same CSS. They sold KrashiMitra to *local* farmers in those countries: the
# US page promised "USDA Zone-Calibrated" planting windows, a "Disease
# Diagnosis Scanner — Live Now", freeze alerts for American counties and
# "80+ North American plant pathogens".
#
# None of that is true. There is no disease scanner (it was dropped on
# request), the weather engine is Indian, and every price on this site comes
# from Agmarknet — an Indian government feed. The pages also carried no
# ads.js, no analytics.js and no shell, so they could not earn or be measured
# even in principle, and they hotlinked 43 photographs from images.unsplash.com
# in a codebase whose rule is that nothing it serves may load an image from
# someone else's server.
#
# THE EVIDENCE THAT DECIDED THE REWRITE. Search Console, 10 Jun - 7 Sep 2026,
# the 127 countries outside India: 6,498 impressions, 24 clicks. Every single
# attributable query is about INDIA —
#
#   USA  1,936 impr / 1 click   "sarkari kisan yojana", "govt kisan yojana"
#   NPL    575 / 5              "मेंथा आयल भाव", "मक्का का भाव उत्तर प्रदेश"
#   ARE    545 / 5              "गेहूं का रेट लखनऊ मंडी", "राजस्थान का नक्शा"
#   SAU    478 / 6              "govt kisan yojana", "सीतापुर का लोकेशन"
#   GBR    293 / 0              "sarkari kisan yojana", "south goa maps"
#   KWT    139 / 4              "नागौर जिले में कुल कितने गांव हैं"
#
# Not one query, from any country, is about farming in that country. So the
# audience is the Indian diaspora and Gulf migrant workers, and the product
# is India's mandi prices, district maps and kisan yojana — not local agronomy.
#
# ── THE LANGUAGE PASS (this file's second job) ───────────────
# The rewrite shipped every page in Hindi with an English gloss, which meant
# /us and /np were the same page twice. They are not any more.
#
# Each country now has a `langs` list: its own official language(s) first,
# then English, then Hindi. langs[0] is what the page SHIPS as — <title>,
# <meta description>, <h1>, `<html lang>`, the nav bar, the FAQ, the JSON-LD
# and every visible string. The rest ride along in a JSON island that a
# toggle in the hero swaps into the DOM.
#
#   /us, /uk, /ca, /ng   English  · Hindi
#   /np                  नेपाली   · English · Hindi
#   /bd                  বাংলা    · English · Hindi
#   /de                  Deutsch  · English · Hindi
#   /id                  Indonesia· English · Hindi
#   /my                  Melayu   · English · Hindi
#   /ae /sa /kw /qa /om  العربية  · English · Hindi   (RTL)
#   /lk                  සිංහල · தமிழ் · English · Hindi   (both officials)
#
# WHY A TOGGLE AND NOT ?lang= OR /np/en. Per multilang-expansion-rejected:
# `?lang=kn` earned 0 impressions in 28 days, and one URL per language would
# multiply 15 pages into ~45 against a site whose measured bottleneck is
# index bloat. So every language lives at the SAME URL, exactly the way
# free_month.card() does it:
#
#   - langs[0] is the served markup; a crawler and a JS-off phone see it and
#     nothing else, byte for byte.
#   - The switch is <button>, never <a> — a link would be a crawlable URL.
#     There is a test asserting this.
#   - The choice is remembered in localStorage under `km_intl_lang`, and the
#     site-wide `km_lang` is honoured as a fallback hint.
#
# WHY HINDI IS ON EVERY PAGE, AND WHY THE CARDS STAY BILINGUAL. Every
# destination page (/bhav, /naksha, /sarkari_yojana) is written in Hindi,
# and the query log above says these visitors are typing Hindi. So each card
# carries the Hindi original on its second line: it tells a Nepali or Arabic
# reader what the page will say when they arrive, and it keeps "मेंथा ऑयल
# भाव" and "गेहूं का रेट" in the indexed markup instead of translating the
# ranking phrases out of it.
#
# NO PHOTOGRAPHS. The old pages leaned on hotlinked stock imagery. Fetching
# and licence-checking fourteen sets of stock photos to decorate a directory
# page is not worth it, and an approximate photo is worse than no photo, so
# the design carries itself on type and colour instead.
#
# HONEST NUMBERS ONLY. 20+ states, 650+ mandis, 150+ crops — the same figures
# /about states. No "50 US States", no "Zones 3-10", no "24/7".
#
#   python tools/build_international.py            # write the pages
#   python tools/build_international.py --check    # non-zero if any is stale
#
# Netlify serves frontend/ statically, so these are FILES, not a server route
# — the same reason /, /mandi and /weather stay static, and the reason this
# is a builder rather than a FastAPI handler. Adding a country is one row in
# COUNTRIES; --redirects prints the _redirects lines it needs. Adding a
# LANGUAGE to an existing country is one entry in that row's `langs` plus a
# column in LABELS/T/FAQ — no new URL, no new sitemap row, no redirect.
# ============================================================

import argparse
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "frontend" / "international"
SITE = "https://krashimitra.in"

TITLE_MAX = 68    # the site-wide SERP budget; Google truncates past this
DESC_MAX = 162    # the site-wide meta-description budget

# ── Languages ────────────────────────────────────────────────
# name/short are what the toggle prints; `dir` flips the content wrapper for
# Arabic; `font` is the extra Google font the script needs (Latin and
# Devanagari are always loaded, so hi/ne/en/id/ms/de need nothing extra).
LANGS = {
    "hi": {"name": "हिन्दी",           "short": "हिं",  "dir": "ltr", "font": None},
    "en": {"name": "English",          "short": "EN",   "dir": "ltr", "font": None},
    "ne": {"name": "नेपाली",           "short": "ने",   "dir": "ltr", "font": None},
    "bn": {"name": "বাংলা",            "short": "বাং",  "dir": "ltr",
           "font": ("Noto+Sans+Bengali:wght@400;600;800", "Noto Sans Bengali")},
    "si": {"name": "සිංහල",            "short": "සිං",  "dir": "ltr",
           "font": ("Noto+Sans+Sinhala:wght@400;600;800", "Noto Sans Sinhala")},
    "ta": {"name": "தமிழ்",            "short": "த",    "dir": "ltr",
           "font": ("Noto+Sans+Tamil:wght@400;600;800", "Noto Sans Tamil")},
    "ar": {"name": "العربية",          "short": "ع",    "dir": "rtl",
           "font": ("Noto+Sans+Arabic:wght@400;600;800", "Noto Sans Arabic")},
    "id": {"name": "Bahasa Indonesia", "short": "ID",   "dir": "ltr", "font": None},
    "ms": {"name": "Bahasa Melayu",    "short": "MS",   "dir": "ltr", "font": None},
    "de": {"name": "Deutsch",          "short": "DE",   "dir": "ltr", "font": None},
}

# The Unicode block each language's own script lives in. A test asserts the
# <title> of a page is actually written in its default language's script —
# a Nepali page whose title came out Latin is the CTR defect this codebase
# already knows about, just in a new place.
SCRIPT_RANGE = {
    "hi": r"[ऀ-ॿ]", "ne": r"[ऀ-ॿ]",
    "bn": r"[ঀ-৿]", "si": r"[඀-෿]",
    "ta": r"[஀-௿]", "ar": r"[؀-ۿ]",
    "en": None, "id": None, "ms": None, "de": None,
}
# ── The link inventory ───────────────────────────────────────
# url -> {lang: label}. Every one is a live page that already earns
# impressions, so the ordering here is evidence rather than taste.
#
# `hi` and `en` are required; a language that is missing falls back to `en`
# and then to `hi` (see `label`). Every destination page is in Hindi, which
# is why the CARD's second line always carries the Hindi original — it tells
# a Nepali or Arabic reader what the page will say when they arrive, and it
# keeps the Hindi phrases those countries actually search for in the indexed
# markup instead of translating them out of it.
LABELS = {
    "/bhav": {
        "hi": "आज का मंडी भाव", "en": "Today's mandi prices",
        "ne": "आजको मण्डी भाउ", "bn": "আজকের মান্ডি দাম",
        "si": "අද මණ්ඩි මිල", "ta": "இன்றைய மண்டி விலை",
        "ar": "أسعار المندي اليوم", "id": "Harga mandi hari ini",
        "ms": "Harga mandi hari ini", "de": "Heutige Mandi-Preise"},
    "/bhav/wheat": {
        "hi": "गेहूं का भाव", "en": "Wheat",
        "ne": "गहुँको भाउ", "bn": "গমের দাম",
        "si": "තිරිඟු මිල", "ta": "கோதுமை விலை",
        "ar": "سعر القمح", "id": "Harga gandum",
        "ms": "Harga gandum", "de": "Weizenpreis"},
    "/bhav/paddy-common": {
        "hi": "धान का भाव", "en": "Paddy",
        "ne": "धानको भाउ", "bn": "ধানের দাম",
        "si": "වී මිල", "ta": "நெல் விலை",
        "ar": "سعر الأرز غير المقشور", "id": "Harga padi",
        "ms": "Harga padi", "de": "Rohreispreis"},
    "/bhav/cotton": {
        "hi": "कपास का भाव", "en": "Cotton",
        "ne": "कपासको भाउ", "bn": "তুলার দাম",
        "si": "කපු මිල", "ta": "பருத்தி விலை",
        "ar": "سعر القطن", "id": "Harga kapas",
        "ms": "Harga kapas", "de": "Baumwollpreis"},
    "/bhav/potato": {
        "hi": "आलू का भाव", "en": "Potato",
        "ne": "आलुको भाउ", "bn": "আলুর দাম",
        "si": "අර්තාපල් මිල", "ta": "உருளைக்கிழங்கு விலை",
        "ar": "سعر البطاطس", "id": "Harga kentang",
        "ms": "Harga kentang", "de": "Kartoffelpreis"},
    "/bhav/onion": {
        "hi": "प्याज का भाव", "en": "Onion",
        "ne": "प्याजको भाउ", "bn": "পেঁয়াজের দাম",
        "si": "ලූනු මිල", "ta": "வெங்காய விலை",
        "ar": "سعر البصل", "id": "Harga bawang merah",
        "ms": "Harga bawang merah", "de": "Zwiebelpreis"},
    "/bhav/mustard": {
        "hi": "सरसों का भाव", "en": "Mustard",
        "ne": "तोरीको भाउ", "bn": "সরিষার দাম",
        "si": "අබ මිල", "ta": "கடுகு விலை",
        "ar": "سعر الخردل", "id": "Harga biji sesawi",
        "ms": "Harga biji sawi", "de": "Senfsaatpreis"},
    "/bhav/maize": {
        "hi": "मक्का का भाव", "en": "Maize",
        "ne": "मकैको भाउ", "bn": "ভুট্টার দাম",
        "si": "බඩඉරිඟු මිල", "ta": "மக்காச்சோள விலை",
        "ar": "سعر الذرة", "id": "Harga jagung",
        "ms": "Harga jagung", "de": "Maispreis"},
    "/bhav/sugarcane": {
        "hi": "गन्ने का भाव", "en": "Sugarcane",
        "ne": "उखुको भाउ", "bn": "আখের দাম",
        "si": "උක් මිල", "ta": "கரும்பு விலை",
        "ar": "سعر قصب السكر", "id": "Harga tebu",
        "ms": "Harga tebu", "de": "Zuckerrohrpreis"},
    "/bhav/mentha-oil": {
        "hi": "मेंथा ऑयल भाव", "en": "Mentha oil",
        "ne": "मेन्था तेलको भाउ", "bn": "মেন্থা তেলের দাম",
        "si": "මෙන්තා තෙල් මිල", "ta": "மெந்தா எண்ணெய் விலை",
        "ar": "سعر زيت المنثا", "id": "Harga minyak mentha",
        "ms": "Harga minyak mentha", "de": "Mentha-Öl-Preis"},
    "/bhav/green-peas": {
        "hi": "मटर का भाव", "en": "Green peas",
        "ne": "केराउको भाउ", "bn": "মটরশুঁটির দাম",
        "si": "පීස් මිල", "ta": "பட்டாணி விலை",
        "ar": "سعر البازلاء", "id": "Harga kacang polong",
        "ms": "Harga kacang pis", "de": "Erbsenpreis"},

    "/naksha": {
        "hi": "भारत के जिलों का नक्शा", "en": "District maps of India",
        "ne": "भारतका जिल्लाको नक्सा", "bn": "ভারতের জেলার মানচিত্র",
        "si": "ඉන්දියාවේ දිස්ත්‍රික් සිතියම්", "ta": "இந்தியாவின் மாவட்ட வரைபடங்கள்",
        "ar": "خرائط مقاطعات الهند", "id": "Peta distrik India",
        "ms": "Peta daerah India", "de": "Distriktkarten Indiens"},
    "/naksha/uttar-pradesh/jile": {
        "hi": "उत्तर प्रदेश के जिले", "en": "UP districts",
        "ne": "उत्तर प्रदेशका जिल्ला", "bn": "উত্তরপ্রদেশের জেলা",
        "si": "උත්තර් ප්‍රදේශ් දිස්ත්‍රික්ක", "ta": "உத்தரப் பிரதேச மாவட்டங்கள்",
        "ar": "مقاطعات أوتار براديش", "id": "Distrik Uttar Pradesh",
        "ms": "Daerah Uttar Pradesh", "de": "Distrikte in Uttar Pradesh"},
    "/naksha/uttar-pradesh/kushinagar": {
        "hi": "कुशीनगर का नक्शा", "en": "Kushinagar map",
        "ne": "कुशीनगरको नक्सा", "bn": "কুশিনগরের মানচিত্র",
        "si": "කුෂිනගර් සිතියම", "ta": "குஷிநகர் வரைபடம்",
        "ar": "خريطة كوشيناغار", "id": "Peta Kushinagar",
        "ms": "Peta Kushinagar", "de": "Karte von Kushinagar"},
    "/naksha/bihar/bhagalpur": {
        "hi": "भागलपुर का नक्शा", "en": "Bhagalpur map",
        "ne": "भागलपुरको नक्सा", "bn": "ভাগলপুরের মানচিত্র",
        "si": "භාගල්පූර් සිතියම", "ta": "பாகல்பூர் வரைபடம்",
        "ar": "خريطة بهاغالبور", "id": "Peta Bhagalpur",
        "ms": "Peta Bhagalpur", "de": "Karte von Bhagalpur"},
    "/naksha/rajasthan/jile": {
        "hi": "राजस्थान के जिले", "en": "Rajasthan districts",
        "ne": "राजस्थानका जिल्ला", "bn": "রাজস্থানের জেলা",
        "si": "රාජස්ථාන් දිස්ත්‍රික්ක", "ta": "ராஜஸ்தான் மாவட்டங்கள்",
        "ar": "مقاطعات راجستان", "id": "Distrik Rajasthan",
        "ms": "Daerah Rajasthan", "de": "Distrikte in Rajasthan"},
    "/naksha/rajasthan/nagaur": {
        "hi": "नागौर का नक्शा", "en": "Nagaur map",
        "ne": "नागौरको नक्सा", "bn": "নাগৌরের মানচিত্র",
        "si": "නාගෞර් සිතියම", "ta": "நாகௌர் வரைபடம்",
        "ar": "خريطة ناغور", "id": "Peta Nagaur",
        "ms": "Peta Nagaur", "de": "Karte von Nagaur"},
    "/naksha/west-bengal/jile": {
        "hi": "पश्चिम बंगाल के जिले", "en": "West Bengal districts",
        "ne": "पश्चिम बंगालका जिल्ला", "bn": "পশ্চিমবঙ্গের জেলা",
        "si": "බටහිර බෙංගාල දිස්ත්‍රික්ක", "ta": "மேற்கு வங்க மாவட்டங்கள்",
        "ar": "مقاطعات البنغال الغربية", "id": "Distrik Benggala Barat",
        "ms": "Daerah Bengal Barat", "de": "Distrikte in Westbengalen"},
    "/naksha/punjab": {
        "hi": "पंजाब का नक्शा", "en": "Punjab map",
        "ne": "पञ्जाबको नक्सा", "bn": "পাঞ্জাবের মানচিত্র",
        "si": "පන්ජාබ් සිතියම", "ta": "பஞ்சாப் வரைபடம்",
        "ar": "خريطة البنجاب", "id": "Peta Punjab",
        "ms": "Peta Punjab", "de": "Karte von Punjab"},
    "/naksha/jharkhand": {
        "hi": "झारखंड का नक्शा", "en": "Jharkhand map",
        "ne": "झारखण्डको नक्सा", "bn": "ঝাড়খণ্ডের মানচিত্র",
        "si": "ජාර්ඛන්ඩ් සිතියම", "ta": "ஜார்கண்ட் வரைபடம்",
        "ar": "خريطة جهارخاند", "id": "Peta Jharkhand",
        "ms": "Peta Jharkhand", "de": "Karte von Jharkhand"},

    "/sarkari_yojana": {
        "hi": "सरकारी किसान योजनाएँ", "en": "Government schemes for farmers",
        "ne": "सरकारी किसान योजना", "bn": "সরকারি কৃষক প্রকল্প",
        "si": "රජයේ ගොවි වැඩසටහන්", "ta": "அரசு விவசாயத் திட்டங்கள்",
        "ar": "برامج الحكومة للمزارعين", "id": "Skema petani pemerintah",
        "ms": "Skim petani kerajaan", "de": "Staatliche Förderprogramme"},
    "/articles/urea-guide-up": {
        "hi": "यूरिया खाद की पूरी गाइड", "en": "Urea guide",
        "ne": "युरिया मलको पूरा गाइड", "bn": "ইউরিয়া সারের পূর্ণ গাইড",
        "si": "යූරියා පොහොර මාර්ගෝපදේශය", "ta": "யூரியா உரம் வழிகாட்டி",
        "ar": "دليل سماد اليوريا", "id": "Panduan pupuk urea",
        "ms": "Panduan baja urea", "de": "Harnstoffdünger-Leitfaden"},
    "/articles/dap-guide-up": {
        "hi": "DAP खाद गाइड", "en": "DAP guide",
        "ne": "DAP मलको गाइड", "bn": "ডিএপি সারের গাইড",
        "si": "DAP පොහොර මාර්ගෝපදේශය", "ta": "DAP உரம் வழிகாட்டி",
        "ar": "دليل سماد DAP", "id": "Panduan pupuk DAP",
        "ms": "Panduan baja DAP", "de": "DAP-Dünger-Leitfaden"},
    "/articles/ganna-rog": {
        "hi": "गन्ने के रोग और इलाज", "en": "Sugarcane diseases",
        "ne": "उखुका रोग र उपचार", "bn": "আখের রোগ ও চিকিৎসা",
        "si": "උක් රෝග හා ප්‍රතිකාර", "ta": "கரும்பு நோய்களும் சிகிச்சையும்",
        "ar": "أمراض قصب السكر وعلاجها", "id": "Penyakit tebu dan penanganannya",
        "ms": "Penyakit tebu dan rawatannya", "de": "Zuckerrohrkrankheiten"},
    "/articles/land-price-up": {
        "hi": "UP में ज़मीन के दाम", "en": "UP land prices",
        "ne": "UP मा जग्गाको भाउ", "bn": "ইউপিতে জমির দাম",
        "si": "UP හි ඉඩම් මිල", "ta": "UP நில விலைகள்",
        "ar": "أسعار الأراضي في أوتار براديش", "id": "Harga tanah di UP",
        "ms": "Harga tanah di UP", "de": "Bodenpreise in Uttar Pradesh"},
    "/articles/": {
        "hi": "खेती की सारी जानकारी", "en": "All farming guides",
        "ne": "खेतीका सबै जानकारी", "bn": "চাষের সব গাইড",
        "si": "ගොවිතැන් මාර්ගෝපදේශ සියල්ල", "ta": "அனைத்து விவசாய வழிகாட்டிகள்",
        "ar": "كل أدلة الزراعة", "id": "Semua panduan bertani",
        "ms": "Semua panduan pertanian", "de": "Alle Anbau-Leitfäden"},
    "/krashi_news": {
        "hi": "कृषि समाचार", "en": "Farm news",
        "ne": "कृषि समाचार", "bn": "কৃষি সংবাদ",
        "si": "කෘෂි පුවත්", "ta": "வேளாண் செய்திகள்",
        "ar": "أخبار الزراعة", "id": "Berita pertanian",
        "ms": "Berita pertanian", "de": "Agrarnachrichten"},
    "/": {
        "hi": "मुख्य", "en": "Home",
        "ne": "गृहपृष्ठ", "bn": "হোম",
        "si": "මුල් පිටුව", "ta": "முகப்பு",
        "ar": "الرئيسية", "id": "Beranda",
        "ms": "Utama", "de": "Startseite"},
    "/about": {
        "hi": "हमारे बारे में", "en": "About us",
        "ne": "हाम्रो बारेमा", "bn": "আমাদের সম্পর্কে",
        "si": "අප ගැන", "ta": "எங்களைப் பற்றி",
        "ar": "من نحن", "id": "Tentang kami",
        "ms": "Tentang kami", "de": "Über uns"},
    "/privacy-policy": {
        "hi": "प्राइवेसी", "en": "Privacy",
        "ne": "गोपनीयता", "bn": "গোপনীয়তা",
        "si": "රහස්‍යතාව", "ta": "தனியுரிமை",
        "ar": "الخصوصية", "id": "Privasi",
        "ms": "Privasi", "de": "Datenschutz"},
}


def label(url: str, lang: str) -> str:
    """The label for `url` in `lang`, falling back en -> hi."""
    e = LABELS[url]
    return e.get(lang) or e.get("en") or e["hi"]

# Everyone gets these three, in this order: the price hub, the map hub and
# the scheme list. They are the three things the international query log is
# made of, so they are the three things above the fold on every page.
CORE = ["/bhav", "/naksha", "/sarkari_yojana"]

# The crop rail, shared by every country, ordered by real impressions.
CROPS = ["/bhav/wheat", "/bhav/paddy-common", "/bhav/mustard", "/bhav/potato",
         "/bhav/onion", "/bhav/cotton", "/bhav/maize", "/bhav/sugarcane"]

READS = ["/articles/urea-guide-up", "/articles/ganna-rog",
         "/articles/land-price-up", "/articles/dap-guide-up"]

# ── The page copy, in every language a country page can offer ──
# One key per visible string. `{c}` is the country's name in that language,
# `{cur}` its currency. A key missing a language falls back to English, but
# a test asserts none is missing for a language some country actually
# defaults to, so the fallback is a safety net rather than a plan.
#
# RICH holds the keys whose value carries markup on purpose; everything else
# is escaped before it reaches the page or the toggle's JSON.
RICH = {"unit_note"}

T = {
"lang_label": {
 "en": "Language", "hi": "भाषा", "ne": "भाषा", "bn": "ভাষা", "si": "භාෂාව",
 "ta": "மொழி", "ar": "اللغة", "id": "Bahasa", "ms": "Bahasa", "de": "Sprache"},

"hero_sub": {
 "en": "Your family farms in India; you are here. Check today's rate before they sell, open the district map, and see which government scheme is running.",
 "hi": "घर भारत में है, आप यहाँ हैं। बिकवाली से पहले आज का भाव देख लीजिए, जिले का नक्शा खोलिए, और कौन-सी सरकारी योजना चल रही है यह जान लीजिए।",
 "ne": "घर भारतमा छ, तपाईं यहाँ हुनुहुन्छ। बेच्नुअघि आजको भाउ हेर्नुहोस्, जिल्लाको नक्सा खोल्नुहोस्, र कुन सरकारी योजना चलिरहेको छ थाहा पाउनुहोस्।",
 "bn": "পরিবার ভারতে চাষ করে, আপনি এখানে। বিক্রির আগে আজকের দাম দেখে নিন, জেলার মানচিত্র খুলুন, আর কোন সরকারি প্রকল্প চলছে জেনে নিন।",
 "si": "ඔබේ පවුල ඉන්දියාවේ ගොවිතැන් කරයි, ඔබ මෙහි සිටී. විකුණන්නට පෙර අද මිල බලන්න, දිස්ත්‍රික් සිතියම විවෘත කරන්න, කුමන රජයේ වැඩසටහන ක්‍රියාත්මක දැයි දැනගන්න.",
 "ta": "உங்கள் குடும்பம் இந்தியாவில் விவசாயம் செய்கிறது, நீங்கள் இங்கே. விற்பதற்கு முன் இன்றைய விலையைப் பாருங்கள், மாவட்ட வரைபடத்தைத் திறங்கள், எந்த அரசுத் திட்டம் நடக்கிறது என்று அறியுங்கள்.",
 "ar": "عائلتك تزرع في الهند وأنت هنا. تحقّق من سعر اليوم قبل البيع، وافتح خريطة المقاطعة، واعرف أي برنامج حكومي قائم الآن.",
 "id": "Keluarga Anda bertani di India, Anda di sini. Cek harga hari ini sebelum mereka menjual, buka peta distrik, dan lihat skema pemerintah yang sedang berjalan.",
 "ms": "Keluarga anda bertani di India, anda di sini. Semak harga hari ini sebelum mereka menjual, buka peta daerah, dan lihat skim kerajaan yang sedang berjalan.",
 "de": "Ihre Familie bewirtschaftet Land in Indien, Sie sind hier. Prüfen Sie den heutigen Preis vor dem Verkauf, öffnen Sie die Distriktkarte und sehen Sie, welches staatliche Programm läuft."},

"stat_mandis": {
 "en": "mandis — daily", "hi": "मंडियाँ — रोज़", "ne": "मण्डी — दैनिक",
 "bn": "মান্ডি — প্রতিদিন", "si": "මණ්ඩි — දිනපතා", "ta": "மண்டிகள் — தினமும்",
 "ar": "سوقاً — يومياً", "id": "mandi — harian", "ms": "mandi — harian",
 "de": "Mandis — täglich"},
"stat_states": {
 "en": "states", "hi": "राज्य", "ne": "राज्य", "bn": "রাজ্য", "si": "ප්‍රාන්ත",
 "ta": "மாநிலங்கள்", "ar": "ولاية", "id": "negara bagian", "ms": "negeri",
 "de": "Bundesstaaten"},
"stat_crops": {
 "en": "crops", "hi": "फसलें", "ne": "बाली", "bn": "ফসল", "si": "බෝග",
 "ta": "பயிர்கள்", "ar": "محصولاً", "id": "komoditas", "ms": "tanaman",
 "de": "Kulturen"},
"stat_free": {
 "en": "no charge", "hi": "कोई शुल्क नहीं", "ne": "नि:शुल्क", "bn": "কোনো খরচ নেই",
 "si": "ගාස්තු නැත", "ta": "கட்டணம் இல்லை", "ar": "بلا رسوم", "id": "tanpa biaya",
 "ms": "tanpa bayaran", "de": "kostenlos"},

"clock_in": {
 "en": "Now in India", "hi": "भारत में अभी", "ne": "भारतमा अहिले", "bn": "ভারতে এখন",
 "si": "ඉන්දියාවේ දැන්", "ta": "இந்தியாவில் இப்போது", "ar": "الآن في الهند",
 "id": "Sekarang di India", "ms": "Sekarang di India", "de": "Jetzt in Indien"},
"clock_here": {
 "en": "Your time", "hi": "आपके यहाँ", "ne": "तपाईंको समय", "bn": "আপনার সময়",
 "si": "ඔබේ වේලාව", "ta": "உங்கள் நேரம்", "ar": "توقيتك", "id": "Waktu Anda",
 "ms": "Waktu anda", "de": "Ihre Zeit"},
"clock_note": {
 "en": "Mandis run on Indian time and the day's rate lands after midday — check this before you call home.",
 "hi": "मंडियाँ भारतीय समय में चलती हैं और दिन का भाव दोपहर के बाद आता है — घर फ़ोन करने से पहले यह देख लीजिए।",
 "ne": "मण्डी भारतीय समयमा चल्छन् र दिनको भाउ दिउँसोपछि आउँछ — घर फोन गर्नुअघि यो हेर्नुहोस्।",
 "bn": "মান্ডি ভারতীয় সময়ে চলে এবং দিনের দাম দুপুরের পরে আসে — বাড়িতে ফোন করার আগে এটি দেখে নিন।",
 "si": "මණ්ඩි ඉන්දියානු වේලාවෙන් ක්‍රියාත්මක වන අතර දවසේ මිල දහවලට පසුව එයි — ගෙදර කතා කරන්නට පෙර මෙය බලන්න.",
 "ta": "மண்டிகள் இந்திய நேரத்தில் இயங்குகின்றன, அன்றைய விலை மதியத்திற்குப் பிறகு வரும் — வீட்டுக்கு அழைப்பதற்கு முன் இதைப் பாருங்கள்.",
 "ar": "تعمل الأسواق بتوقيت الهند ويصدر سعر اليوم بعد الظهر — تحقّق من هذا قبل الاتصال بالأهل.",
 "id": "Mandi beroperasi dengan waktu India dan harga harian keluar setelah tengah hari — cek ini sebelum menelepon ke rumah.",
 "ms": "Mandi beroperasi mengikut waktu India dan harga harian keluar selepas tengah hari — semak ini sebelum menelefon ke rumah.",
 "de": "Mandis handeln nach indischer Zeit, der Tagespreis kommt nach Mittag — prüfen Sie das, bevor Sie zu Hause anrufen."},

"s_top_h": {
 "en": "The three things people abroad open most",
 "hi": "तीन चीज़ें जो लोग यहाँ से सबसे ज़्यादा देखते हैं",
 "ne": "विदेशबाट सबैभन्दा बढी खोलिने तीन कुरा",
 "bn": "বিদেশ থেকে সবচেয়ে বেশি যে তিনটি খোলা হয়",
 "si": "විදේශයේ සිටින අය වැඩිපුරම විවෘත කරන දේ තුන",
 "ta": "வெளிநாட்டிலிருந்து அதிகம் திறக்கப்படும் மூன்று",
 "ar": "أكثر ثلاثة أشياء يفتحها المغتربون",
 "id": "Tiga hal yang paling sering dibuka dari luar negeri",
 "ms": "Tiga perkara yang paling kerap dibuka dari luar negara",
 "de": "Die drei meistgeöffneten Seiten aus dem Ausland"},
"s_top_sub": {
 "en": "Prices, district maps, and the scheme list.",
 "hi": "भाव, जिलों के नक्शे और योजनाओं की सूची।",
 "ne": "भाउ, जिल्लाको नक्सा र योजनाको सूची।",
 "bn": "দাম, জেলার মানচিত্র আর প্রকল্পের তালিকা।",
 "si": "මිල, දිස්ත්‍රික් සිතියම් සහ වැඩසටහන් ලැයිස්තුව.",
 "ta": "விலைகள், மாவட்ட வரைபடங்கள், திட்டப் பட்டியல்.",
 "ar": "الأسعار وخرائط المقاطعات وقائمة البرامج.",
 "id": "Harga, peta distrik, dan daftar skema.",
 "ms": "Harga, peta daerah dan senarai skim.",
 "de": "Preise, Distriktkarten und die Programmliste."},

"s_price_h": {
 "en": "Today's rate — pick a crop", "hi": "आज का भाव — फसल चुनिए",
 "ne": "आजको भाउ — बाली छान्नुहोस्", "bn": "আজকের দাম — ফসল বাছুন",
 "si": "අද මිල — බෝගයක් තෝරන්න", "ta": "இன்றைய விலை — பயிரைத் தேர்வுசெய்யுங்கள்",
 "ar": "سعر اليوم — اختر محصولاً", "id": "Harga hari ini — pilih komoditas",
 "ms": "Harga hari ini — pilih tanaman", "de": "Heutiger Preis — Kultur wählen"},
"s_price_sub": {
 "en": "Live rates from Agmarknet, the Government of India feed. Updated every day.",
 "hi": "भाव भारत सरकार के Agmarknet फ़ीड से आता है। हर दिन अपने आप अपडेट।",
 "ne": "भाउ भारत सरकारको Agmarknet फिडबाट आउँछ। हरेक दिन आफैं अपडेट।",
 "bn": "দাম আসে ভারত সরকারের Agmarknet ফিড থেকে। প্রতিদিন নিজে থেকেই আপডেট।",
 "si": "මිල ලැබෙන්නේ ඉන්දීය රජයේ Agmarknet දත්ත සමුදායෙනි. දිනපතා ස්වයංක්‍රීයව යාවත්කාලීන වේ.",
 "ta": "விலைகள் இந்திய அரசின் Agmarknet ஊட்டத்திலிருந்து. தினமும் தானாகப் புதுப்பிக்கப்படும்.",
 "ar": "الأسعار من Agmarknet، تغذية الحكومة الهندية. تُحدَّث كل يوم تلقائياً.",
 "id": "Harga berasal dari Agmarknet, umpan data Pemerintah India. Diperbarui setiap hari.",
 "ms": "Harga daripada Agmarknet, suapan data Kerajaan India. Dikemas kini setiap hari.",
 "de": "Preise aus Agmarknet, dem Datenfeed der indischen Regierung. Täglich aktualisiert."},

"s_unit_h": {
 "en": "What ₹ per quintal means", "hi": "₹ प्रति क्विंटल का मतलब",
 "ne": "₹ प्रति क्विन्टलको अर्थ", "bn": "₹ প্রতি কুইন্টাল মানে কী",
 "si": "₹ ක්වින්ටල් එකකට යනු කුමක්ද", "ta": "₹ ஒரு குவிண்டாலுக்கு என்றால் என்ன",
 "ar": "ماذا يعني ₹ للقنطار", "id": "Arti ₹ per kuintal",
 "ms": "Maksud ₹ sekuintal", "de": "Was ₹ pro Quintal bedeutet"},
"s_unit_sub": {
 "en": "Reading an Indian price from {c}.", "hi": "{c} से भारत का भाव पढ़ना।",
 "ne": "{c}बाट भारतको भाउ पढ्ने तरिका।", "bn": "{c} থেকে ভারতের দাম পড়া।",
 "si": "{c} සිට ඉන්දියානු මිලක් කියවීම.", "ta": "{c} இருந்து இந்திய விலையைப் படிப்பது.",
 "ar": "كيف تقرأ سعراً هندياً من {c}.", "id": "Membaca harga India dari {c}.",
 "ms": "Membaca harga India dari {c}.", "de": "Einen indischen Preis aus {c} lesen."},
"unit_note": {
 "en": "Indian rates are quoted in <b>₹ per quintal</b>. <b>1 quintal = 100 kg = about 220.5 lb</b>. So ₹2,400 per quintal means ₹24 per kg.",
 "hi": "भारत में भाव <b>₹ प्रति क्विंटल</b> में लिखा जाता है। <b>1 क्विंटल = 100 किलो = लगभग 220.5 पाउंड</b>। तो ₹2,400 प्रति क्विंटल का मतलब है ₹24 प्रति किलो।",
 "ne": "भारतमा भाउ <b>₹ प्रति क्विन्टल</b>मा लेखिन्छ। <b>१ क्विन्टल = १०० किलो = करिब २२०.५ पाउन्ड</b>। त्यसैले ₹२,४०० प्रति क्विन्टल भनेको ₹२४ प्रति किलो हो।",
 "bn": "ভারতে দাম লেখা হয় <b>₹ প্রতি কুইন্টাল</b>-এ। <b>১ কুইন্টাল = ১০০ কেজি = প্রায় ২২০.৫ পাউন্ড</b>। অর্থাৎ ₹২,৪০০ প্রতি কুইন্টাল মানে ₹২৪ প্রতি কেজি।",
 "si": "ඉන්දියාවේ මිල ලියන්නේ <b>₹ ක්වින්ටල් එකකට</b> ලෙසිනි. <b>ක්වින්ටල් 1 = කිලෝ 100 = ආසන්න වශයෙන් රාත්තල් 220.5</b>. එනම් ක්වින්ටලයකට ₹2,400 යනු කිලෝවකට ₹24 කි.",
 "ta": "இந்தியாவில் விலை <b>₹ ஒரு குவிண்டாலுக்கு</b> என்று குறிக்கப்படுகிறது. <b>1 குவிண்டால் = 100 கிலோ = சுமார் 220.5 பவுண்டு</b>. அதாவது குவிண்டாலுக்கு ₹2,400 என்றால் கிலோவுக்கு ₹24.",
 "ar": "تُذكر الأسعار الهندية بـ<b>₹ للقنطار</b>. <b>القنطار = 100 كجم = نحو 220.5 رطلاً</b>. أي أن ₹2,400 للقنطار تعني ₹24 للكيلوغرام.",
 "id": "Harga India dinyatakan dalam <b>₹ per kuintal</b>. <b>1 kuintal = 100 kg = sekitar 220,5 pon</b>. Jadi ₹2.400 per kuintal berarti ₹24 per kg.",
 "ms": "Harga India dinyatakan dalam <b>₹ sekuintal</b>. <b>1 kuintal = 100 kg = kira-kira 220.5 paun</b>. Jadi ₹2,400 sekuintal bermakna ₹24 sekilogram.",
 "de": "Indische Preise werden in <b>₹ pro Quintal</b> angegeben. <b>1 Quintal = 100 kg = rund 220,5 Pfund</b>. ₹2.400 pro Quintal sind also ₹24 pro Kilo."},
"unit_note2": {
 "en": "Convert to {cur} at your bank's rate — we do not publish an exchange rate, because a stale one would be a wrong number.",
 "hi": "{cur} में बदलने के लिए अपने बैंक की दर लगाइए — हम विनिमय दर नहीं छापते, क्योंकि पुरानी दर गलत आँकड़ा होगी।",
 "ne": "{cur}मा बदल्न आफ्नो बैंकको दर प्रयोग गर्नुहोस् — हामी विनिमय दर छाप्दैनौं, किनभने पुरानो दर गलत अंक हुनेछ।",
 "bn": "{cur}-এ বদলাতে আপনার ব্যাংকের হার ব্যবহার করুন — আমরা বিনিময় হার প্রকাশ করি না, কারণ পুরোনো হার ভুল সংখ্যা হবে।",
 "si": "{cur} බවට හරවන්න ඔබේ බැංකුවේ අනුපාතය භාවිත කරන්න — අපි විනිමය අනුපාතයක් පළ නොකරමු, පරණ එකක් වැරදි අගයක් වන බැවිනි.",
 "ta": "{cur} ஆக மாற்ற உங்கள் வங்கியின் விகிதத்தைப் பயன்படுத்துங்கள் — நாங்கள் மாற்று விகிதம் வெளியிடுவதில்லை, பழையது தவறான எண்ணாகிவிடும்.",
 "ar": "حوّل إلى {cur} بسعر مصرفك — نحن لا ننشر سعر صرف، لأن سعراً قديماً سيكون رقماً خاطئاً.",
 "id": "Konversikan ke {cur} dengan kurs bank Anda — kami tidak menerbitkan kurs, karena kurs basi adalah angka yang salah.",
 "ms": "Tukar kepada {cur} pada kadar bank anda — kami tidak menerbitkan kadar tukaran, kerana kadar lapuk ialah angka yang salah.",
 "de": "Rechnen Sie zum Kurs Ihrer Bank in {cur} um — wir veröffentlichen keinen Wechselkurs, denn ein veralteter wäre eine falsche Zahl."},

"s_seen_h": {
 "en": "Most-opened pages from {c}", "hi": "{c} से सबसे ज़्यादा देखे गए पन्ने",
 "ne": "{c}बाट सबैभन्दा बढी हेरिएका पृष्ठ", "bn": "{c} থেকে সবচেয়ে বেশি খোলা পাতা",
 "si": "{c} සිට වැඩිපුරම විවෘත කළ පිටු", "ta": "{c} இருந்து அதிகம் திறக்கப்பட்ட பக்கங்கள்",
 "ar": "أكثر الصفحات فتحاً من {c}", "id": "Halaman paling sering dibuka dari {c}",
 "ms": "Halaman paling kerap dibuka dari {c}", "de": "Meistgeöffnete Seiten aus {c}"},
"s_seen_sub": {
 "en": "What visitors from {c} actually read.", "hi": "{c} से आने वाले लोग असल में यही पढ़ते हैं।",
 "ne": "{c}बाट आउनेहरूले वास्तवमा यही पढ्छन्।", "bn": "{c} থেকে আসা মানুষ আসলে এগুলোই পড়েন।",
 "si": "{c} සිට එන අය සැබවින්ම කියවන්නේ මේවාය.", "ta": "{c} இருந்து வருபவர்கள் உண்மையில் படிப்பவை.",
 "ar": "ما يقرأه فعلاً الزوار من {c}.", "id": "Yang benar-benar dibaca pengunjung dari {c}.",
 "ms": "Apa yang benar-benar dibaca pelawat dari {c}.", "de": "Was Besucher aus {c} tatsächlich lesen."},

"s_maps_h": {
 "en": "District maps", "hi": "जिलों का नक्शा", "ne": "जिल्लाको नक्सा",
 "bn": "জেলার মানচিত্র", "si": "දිස්ත්‍රික් සිතියම්", "ta": "மாவட்ட வரைபடங்கள்",
 "ar": "خرائط المقاطعات", "id": "Peta distrik", "ms": "Peta daerah",
 "de": "Distriktkarten"},
"s_maps_sub": {
 "en": "Every district of India, with a downloadable map — useful when you are filling a form from abroad.",
 "hi": "भारत का हर जिला, डाउनलोड होने वाले नक्शे के साथ — विदेश से फ़ॉर्म भरते वक़्त काम आता है।",
 "ne": "भारतको हरेक जिल्ला, डाउनलोड गर्न मिल्ने नक्सासहित — विदेशबाट फारम भर्दा काम लाग्छ।",
 "bn": "ভারতের প্রতিটি জেলা, ডাউনলোডযোগ্য মানচিত্রসহ — বিদেশ থেকে ফর্ম ভরার সময় কাজে লাগে।",
 "si": "ඉන්දියාවේ සෑම දිස්ත්‍රික්කයක්ම, බාගත කළ හැකි සිතියමක් සමඟ — විදේශයක සිට ආකෘති පත්‍රයක් පුරවන විට ප්‍රයෝජනවත්.",
 "ta": "இந்தியாவின் ஒவ்வொரு மாவட்டமும், பதிவிறக்கக்கூடிய வரைபடத்துடன் — வெளிநாட்டிலிருந்து படிவம் நிரப்பும்போது பயன்படும்.",
 "ar": "كل مقاطعة في الهند مع خريطة قابلة للتنزيل — مفيدة عند تعبئة استمارة من الخارج.",
 "id": "Setiap distrik India, dengan peta yang bisa diunduh — berguna saat mengisi formulir dari luar negeri.",
 "ms": "Setiap daerah India, dengan peta boleh muat turun — berguna semasa mengisi borang dari luar negara.",
 "de": "Jeder Distrikt Indiens mit herunterladbarer Karte — nützlich beim Ausfüllen eines Formulars aus dem Ausland."},

"s_read_h": {
 "en": "Worth reading", "hi": "पढ़ने के लिए", "ne": "पढ्नका लागि", "bn": "পড়ার জন্য",
 "si": "කියවීමට වටී", "ta": "படிக்க வேண்டியவை", "ar": "يستحق القراءة",
 "id": "Layak dibaca", "ms": "Wajar dibaca", "de": "Lesenswert"},
"s_read_sub": {
 "en": "The guides Indian farmers read most.",
 "hi": "भारतीय किसान सबसे ज़्यादा यही गाइड पढ़ते हैं।",
 "ne": "भारतीय किसानले सबैभन्दा बढी पढ्ने गाइड।",
 "bn": "ভারতীয় কৃষকরা সবচেয়ে বেশি যে গাইডগুলো পড়েন।",
 "si": "ඉන්දීය ගොවීන් වැඩිපුරම කියවන මාර්ගෝපදේශ.",
 "ta": "இந்திய விவசாயிகள் அதிகம் படிக்கும் வழிகாட்டிகள்.",
 "ar": "الأدلة التي يقرأها المزارعون الهنود أكثر من غيرها.",
 "id": "Panduan yang paling banyak dibaca petani India.",
 "ms": "Panduan yang paling banyak dibaca petani India.",
 "de": "Die Leitfäden, die indische Bauern am häufigsten lesen."},

"s_faq_h": {
 "en": "Common questions · FAQ", "hi": "आम सवाल · FAQ", "ne": "सामान्य प्रश्न · FAQ",
 "bn": "সাধারণ প্রশ্ন · FAQ", "si": "පොදු ප්‍රශ්න · FAQ", "ta": "பொதுவான கேள்விகள் · FAQ",
 "ar": "أسئلة شائعة · FAQ", "id": "Pertanyaan umum · FAQ", "ms": "Soalan lazim · FAQ",
 "de": "Häufige Fragen · FAQ"},

"s_other_h": {
 "en": "Other countries", "hi": "दूसरे देश", "ne": "अन्य देश", "bn": "অন্যান্য দেশ",
 "si": "වෙනත් රටවල්", "ta": "பிற நாடுகள்", "ar": "دول أخرى", "id": "Negara lain",
 "ms": "Negara lain", "de": "Andere Länder"},
"s_other_sub": {
 "en": "Pick where you are.", "hi": "आप जहाँ हैं वह देश चुनिए।",
 "ne": "तपाईं जहाँ हुनुहुन्छ त्यो देश छान्नुहोस्।", "bn": "আপনি যেখানে আছেন সেই দেশ বাছুন।",
 "si": "ඔබ සිටින රට තෝරන්න.", "ta": "நீங்கள் இருக்கும் நாட்டைத் தேர்வுசெய்யுங்கள்.",
 "ar": "اختر البلد الذي أنت فيه.", "id": "Pilih tempat Anda berada.",
 "ms": "Pilih tempat anda berada.", "de": "Wählen Sie, wo Sie sind."},
"all_countries": {
 "en": "All countries", "hi": "सभी देश", "ne": "सबै देश", "bn": "সব দেশ",
 "si": "සියලු රටවල්", "ta": "அனைத்து நாடுகளும்", "ar": "كل الدول",
 "id": "Semua negara", "ms": "Semua negara", "de": "Alle Länder"},

"cta_h": {
 "en": "Your home mandi, from right here", "hi": "घर की मंडी, यहीं से",
 "ne": "घरको मण्डी, यहीँबाट", "bn": "বাড়ির মান্ডি, এখান থেকেই",
 "si": "ඔබේ ගමේ මණ්ඩිය, මෙතැනින්ම", "ta": "உங்கள் ஊர் மண்டி, இங்கிருந்தே",
 "ar": "سوق بلدك، من هنا", "id": "Mandi kampung halaman, dari sini",
 "ms": "Mandi kampung halaman, dari sini", "de": "Ihre Heimat-Mandi, von hier aus"},
"cta_p": {
 "en": "No login, no charge. Rates update themselves every day.",
 "hi": "कोई लॉगिन नहीं, कोई शुल्क नहीं। भाव रोज़ अपने आप अपडेट होता है।",
 "ne": "कुनै लगइन छैन, कुनै शुल्क छैन। भाउ हरेक दिन आफैं अपडेट हुन्छ।",
 "bn": "কোনো লগইন নেই, কোনো খরচ নেই। দাম প্রতিদিন নিজে থেকেই আপডেট হয়।",
 "si": "පිවිසුමක් නැත, ගාස්තුවක් නැත. මිල දිනපතා ස්වයංක්‍රීයව යාවත්කාලීන වේ.",
 "ta": "உள்நுழைவு இல்லை, கட்டணம் இல்லை. விலைகள் தினமும் தானாகப் புதுப்பிக்கப்படும்.",
 "ar": "بلا تسجيل دخول وبلا رسوم. الأسعار تُحدَّث تلقائياً كل يوم.",
 "id": "Tanpa login, tanpa biaya. Harga diperbarui sendiri setiap hari.",
 "ms": "Tanpa log masuk, tanpa bayaran. Harga dikemas kini sendiri setiap hari.",
 "de": "Kein Login, keine Gebühr. Die Preise aktualisieren sich täglich von selbst."},
"cta_btn": {
 "en": "See today's rate", "hi": "आज का भाव देखिए", "ne": "आजको भाउ हेर्नुहोस्",
 "bn": "আজকের দাম দেখুন", "si": "අද මිල බලන්න", "ta": "இன்றைய விலையைப் பாருங்கள்",
 "ar": "اطّلع على سعر اليوم", "id": "Lihat harga hari ini", "ms": "Lihat harga hari ini",
 "de": "Heutigen Preis ansehen"},

"menu": {
 "en": "Menu", "hi": "मेनु", "ne": "मेनु", "bn": "মেনু", "si": "මෙනුව",
 "ta": "மெனு", "ar": "القائمة", "id": "Menu", "ms": "Menu", "de": "Menü"},
"email_line": {
 "en": "KrashiMitra email: krashimitra038@gmail.com",
 "hi": "कृषिमित्र ईमेल: krashimitra038@gmail.com",
 "ne": "कृषिमित्र इमेल: krashimitra038@gmail.com",
 "bn": "কৃষিমিত্র ইমেল: krashimitra038@gmail.com",
 "si": "KrashiMitra ඊමේල්: krashimitra038@gmail.com",
 "ta": "கிருஷிமித்ரா மின்னஞ்சல்: krashimitra038@gmail.com",
 "ar": "بريد كريشي ميترا: krashimitra038@gmail.com",
 "id": "Email KrashiMitra: krashimitra038@gmail.com",
 "ms": "E-mel KrashiMitra: krashimitra038@gmail.com",
 "de": "KrashiMitra-E-Mail: krashimitra038@gmail.com"},
"footer_note": {
 "en": "© 2026 KrashiMitra.in — built for Indian farmers. Mandi prices come from the Government of India's Agmarknet (data.gov.in) feed and update themselves every day.",
 "hi": "© 2026 KrashiMitra.in — भारतीय किसानों के लिए बनाया गया। मंडी भाव भारत सरकार के Agmarknet (data.gov.in) फ़ीड से, हर दिन अपने आप अपडेट।",
 "ne": "© 2026 KrashiMitra.in — भारतीय किसानका लागि बनाइएको। मण्डी भाउ भारत सरकारको Agmarknet (data.gov.in) फिडबाट, हरेक दिन आफैं अपडेट।",
 "bn": "© 2026 KrashiMitra.in — ভারতীয় কৃষকদের জন্য তৈরি। মান্ডি দাম ভারত সরকারের Agmarknet (data.gov.in) ফিড থেকে, প্রতিদিন নিজে থেকেই আপডেট।",
 "si": "© 2026 KrashiMitra.in — ඉන්දීය ගොවීන් සඳහා තැනූවකි. මණ්ඩි මිල ලැබෙන්නේ ඉන්දීය රජයේ Agmarknet (data.gov.in) දත්තවලින්, දිනපතා ස්වයංක්‍රීයව යාවත්කාලීන වේ.",
 "ta": "© 2026 KrashiMitra.in — இந்திய விவசாயிகளுக்காக உருவாக்கப்பட்டது. மண்டி விலைகள் இந்திய அரசின் Agmarknet (data.gov.in) ஊட்டத்திலிருந்து, தினமும் தானாகப் புதுப்பிக்கப்படும்.",
 "ar": "© 2026 KrashiMitra.in — صُنع من أجل المزارعين الهنود. أسعار المندي من تغذية Agmarknet (data.gov.in) الحكومية الهندية، وتُحدَّث تلقائياً كل يوم.",
 "id": "© 2026 KrashiMitra.in — dibuat untuk petani India. Harga mandi berasal dari umpan Agmarknet (data.gov.in) Pemerintah India dan diperbarui setiap hari.",
 "ms": "© 2026 KrashiMitra.in — dibina untuk petani India. Harga mandi daripada suapan Agmarknet (data.gov.in) Kerajaan India dan dikemas kini setiap hari.",
 "de": "© 2026 KrashiMitra.in — für indische Bauern gebaut. Die Mandi-Preise stammen aus dem Agmarknet-Feed (data.gov.in) der indischen Regierung und aktualisieren sich täglich."},
}
# ── FAQ ──────────────────────────────────────────────────────
# One source for both the visible markup and the JSON-LD, per language, so
# the two can never drift apart — the rule the article builder and bhav.py's
# _faq() already follow. `{c}` is the country in that language.
FAQ = {
"en": [
 ("Can I check India's mandi prices from {c}?",
  "Yes. KrashiMitra opens from any country and never asks for a login. Prices come from the Government of India's Agmarknet feed and update themselves every day."),
 ("What unit are the prices in?",
  "All prices are in ₹ per quintal. 1 quintal = 100 kg = about 220.5 lb. So ₹2,400 per quintal means ₹24 per kg."),
 ("When do the prices update?",
  "Mandis trade on Indian Standard Time and the day's rates arrive between afternoon and evening. The clock above shows India's time right now, so you know when to call home."),
 ("Does this give advice for farming in {c}?",
  "No. Every figure here is Indian — Indian mandis, Indian districts and Government of India schemes. For soil, weather or crops in {c}, ask the local agricultural service there."),
 ("Is there any charge?",
  "No. Mandi prices, maps, scheme information and farming guides are all free."),
],
"hi": [
 ("क्या {c} से भारत का मंडी भाव देखा जा सकता है?",
  "हाँ। KrashiMitra किसी भी देश से खुलता है और कोई लॉगिन नहीं माँगता। भाव भारत सरकार के Agmarknet फ़ीड से आता है और हर दिन अपने आप अपडेट होता है।"),
 ("भाव किस इकाई में होता है?",
  "सारे भाव ₹ प्रति क्विंटल में हैं। 1 क्विंटल = 100 किलोग्राम = लगभग 220.5 पाउंड। यानी ₹2,400 प्रति क्विंटल का मतलब ₹24 प्रति किलो है।"),
 ("भाव कब अपडेट होता है?",
  "मंडियाँ भारतीय समय (IST) में कारोबार करती हैं और दिन के भाव दोपहर से शाम के बीच आते हैं। ऊपर दी गई घड़ी में भारत का अभी का समय दिख रहा है, ताकि घर फ़ोन करने का सही वक़्त पता चले।"),
 ("क्या यह {c} की खेती के लिए सलाह देता है?",
  "नहीं। यहाँ का सारा डेटा भारत का है — भारतीय मंडियाँ, भारतीय जिले और भारत सरकार की योजनाएँ। {c} की मिट्टी, मौसम या फसल के लिए वहाँ की स्थानीय कृषि सेवा से ही सलाह लें।"),
 ("क्या इसका कोई शुल्क है?",
  "नहीं। मंडी भाव, नक्शे, योजनाओं की जानकारी और खेती की गाइड — सब मुफ़्त हैं।"),
],
"ne": [
 ("के {c}बाट भारतको मण्डी भाउ हेर्न सकिन्छ?",
  "सकिन्छ। KrashiMitra जुनसुकै देशबाट खुल्छ र लगइन माग्दैन। भाउ भारत सरकारको Agmarknet फिडबाट आउँछ र हरेक दिन आफैं अपडेट हुन्छ।"),
 ("भाउ कुन एकाइमा हुन्छ?",
  "सबै भाउ ₹ प्रति क्विन्टलमा छन्। १ क्विन्टल = १०० किलो = करिब २२०.५ पाउन्ड। अर्थात् ₹२,४०० प्रति क्विन्टल भनेको ₹२४ प्रति किलो हो।"),
 ("भाउ कहिले अपडेट हुन्छ?",
  "मण्डीहरू भारतीय समय (IST) मा कारोबार गर्छन् र दिनको भाउ दिउँसोदेखि साँझको बीचमा आउँछ। माथिको घडीमा भारतको अहिलेको समय देखिन्छ, ताकि घर फोन गर्ने ठीक बेला थाहा होस्।"),
 ("के यसले {c}को खेतीका लागि सल्लाह दिन्छ?",
  "दिँदैन। यहाँको सबै डेटा भारतको हो — भारतीय मण्डी, भारतीय जिल्ला र भारत सरकारका योजना। {c}को माटो, मौसम वा बालीका लागि त्यहीँको स्थानीय कृषि सेवासँग सल्लाह लिनुहोस्।"),
 ("के यसको कुनै शुल्क छ?",
  "छैन। मण्डी भाउ, नक्सा, योजनाको जानकारी र खेतीका गाइड — सबै नि:शुल्क छन्।"),
],
"bn": [
 ("{c} থেকে কি ভারতের মান্ডি দাম দেখা যায়?",
  "হ্যাঁ। KrashiMitra যেকোনো দেশ থেকে খোলে এবং কখনো লগইন চায় না। দাম আসে ভারত সরকারের Agmarknet ফিড থেকে এবং প্রতিদিন নিজে থেকেই আপডেট হয়।"),
 ("দাম কোন এককে দেওয়া?",
  "সব দাম ₹ প্রতি কুইন্টালে। ১ কুইন্টাল = ১০০ কেজি = প্রায় ২২০.৫ পাউন্ড। অর্থাৎ ₹২,৪০০ প্রতি কুইন্টাল মানে ₹২৪ প্রতি কেজি।"),
 ("দাম কখন আপডেট হয়?",
  "মান্ডিগুলো ভারতীয় সময়ে (IST) কারবার করে এবং দিনের দাম দুপুর থেকে সন্ধ্যার মধ্যে আসে। উপরের ঘড়িতে ভারতের এখনকার সময় দেখাচ্ছে, যাতে বাড়িতে ফোন করার সঠিক সময় বোঝা যায়।"),
 ("এটি কি {c}-এর চাষের জন্য পরামর্শ দেয়?",
  "না। এখানকার সব তথ্য ভারতের — ভারতীয় মান্ডি, ভারতীয় জেলা আর ভারত সরকারের প্রকল্প। {c}-এর মাটি, আবহাওয়া বা ফসলের জন্য সেখানকার স্থানীয় কৃষি সেবার পরামর্শ নিন।"),
 ("এর কি কোনো খরচ আছে?",
  "না। মান্ডি দাম, মানচিত্র, প্রকল্পের তথ্য আর চাষের গাইড — সবই বিনামূল্যে।"),
],
"si": [
 ("{c} සිට ඉන්දියාවේ මණ්ඩි මිල බැලිය හැකිද?",
  "ඔව්. KrashiMitra ඕනෑම රටකින් විවෘත වන අතර කිසිදු පිවිසුමක් ඉල්ලන්නේ නැත. මිල ලැබෙන්නේ ඉන්දීය රජයේ Agmarknet දත්තවලින් වන අතර දිනපතා ස්වයංක්‍රීයව යාවත්කාලීන වේ."),
 ("මිල දක්වා ඇත්තේ කුමන ඒකකයෙන්ද?",
  "සියලු මිල ₹ ක්වින්ටල් එකකට වේ. ක්වින්ටල් 1 = කිලෝ 100 = ආසන්න වශයෙන් රාත්තල් 220.5. එනම් ක්වින්ටලයකට ₹2,400 යනු කිලෝවකට ₹24 කි."),
 ("මිල යාවත්කාලීන වන්නේ කවදාද?",
  "මණ්ඩි ගනුදෙනු කරන්නේ ඉන්දීය සම්මත වේලාවෙන් (IST) වන අතර දවසේ මිල දහවලේ සිට සවස දක්වා ලැබේ. ඉහත ඔරලෝසුවේ ඉන්දියාවේ දැන් වේලාව පෙනේ, එවිට ගෙදර කතා කරන නියම වේලාව දැනගත හැක."),
 ("මෙය {c} හි ගොවිතැන සඳහා උපදෙස් දෙයිද?",
  "නැත. මෙහි ඇති සියලු දත්ත ඉන්දියාවේ ය — ඉන්දීය මණ්ඩි, ඉන්දීය දිස්ත්‍රික්ක සහ ඉන්දීය රජයේ වැඩසටහන්. {c} හි පස, කාලගුණය හෝ බෝග සඳහා එහි ඇති දේශීය කෘෂිකර්ම සේවයෙන් උපදෙස් ලබාගන්න."),
 ("කිසියම් ගාස්තුවක් තිබේද?",
  "නැත. මණ්ඩි මිල, සිතියම්, වැඩසටහන් තොරතුරු සහ ගොවිතැන් මාර්ගෝපදේශ — සියල්ල නොමිලේ."),
],
"ta": [
 ("{c} இருந்து இந்தியாவின் மண்டி விலையைப் பார்க்க முடியுமா?",
  "ஆம். KrashiMitra எந்த நாட்டிலிருந்தும் திறக்கும், உள்நுழைவு கேட்காது. விலைகள் இந்திய அரசின் Agmarknet ஊட்டத்திலிருந்து வருகின்றன, தினமும் தானாகப் புதுப்பிக்கப்படுகின்றன."),
 ("விலைகள் எந்த அலகில் உள்ளன?",
  "அனைத்து விலைகளும் ₹ ஒரு குவிண்டாலுக்கு. 1 குவிண்டால் = 100 கிலோ = சுமார் 220.5 பவுண்டு. அதாவது குவிண்டாலுக்கு ₹2,400 என்றால் கிலோவுக்கு ₹24."),
 ("விலைகள் எப்போது புதுப்பிக்கப்படும்?",
  "மண்டிகள் இந்திய நேரத்தில் (IST) வணிகம் செய்கின்றன, அன்றைய விலைகள் மதியத்திற்கும் மாலைக்கும் இடையில் வரும். மேலே உள்ள கடிகாரம் இந்தியாவின் தற்போதைய நேரத்தைக் காட்டுகிறது, வீட்டுக்கு அழைக்கும் சரியான நேரம் தெரியும்."),
 ("இது {c} விவசாயத்திற்கு ஆலோசனை தருகிறதா?",
  "இல்லை. இங்குள்ள அனைத்துத் தரவும் இந்தியாவினுடையது — இந்திய மண்டிகள், இந்திய மாவட்டங்கள், இந்திய அரசுத் திட்டங்கள். {c} மண், வானிலை அல்லது பயிர்களுக்கு அங்குள்ள உள்ளூர் வேளாண் சேவையிடம் ஆலோசனை பெறுங்கள்."),
 ("இதற்கு ஏதேனும் கட்டணம் உண்டா?",
  "இல்லை. மண்டி விலைகள், வரைபடங்கள், திட்டத் தகவல், விவசாய வழிகாட்டிகள் — அனைத்தும் இலவசம்."),
],
"ar": [
 ("هل يمكن الاطلاع على أسعار المندي الهندية من {c}؟",
  "نعم. يفتح KrashiMitra من أي بلد ولا يطلب تسجيل دخول أبداً. الأسعار تأتي من تغذية Agmarknet الحكومية الهندية وتُحدَّث تلقائياً كل يوم."),
 ("بأي وحدة تُذكر الأسعار؟",
  "كل الأسعار بـ₹ للقنطار. القنطار = 100 كجم = نحو 220.5 رطلاً. أي أن ₹2,400 للقنطار تعني ₹24 للكيلوغرام."),
 ("متى تُحدَّث الأسعار؟",
  "تتداول الأسواق بالتوقيت الهندي القياسي (IST) وتصل أسعار اليوم بين الظهيرة والمساء. الساعة أعلاه تُظهر توقيت الهند الآن، لتعرف الوقت المناسب للاتصال بالأهل."),
 ("هل يقدّم هذا نصائح للزراعة في {c}؟",
  "لا. كل البيانات هنا هندية — أسواق هندية ومقاطعات هندية وبرامج الحكومة الهندية. أما تربة {c} وطقسها ومحاصيلها فاسأل عنها الخدمة الزراعية المحلية هناك."),
 ("هل هناك أي رسوم؟",
  "لا. أسعار المندي والخرائط ومعلومات البرامج وأدلة الزراعة — كلها مجانية."),
],
"id": [
 ("Bisakah saya melihat harga mandi India dari {c}?",
  "Bisa. KrashiMitra terbuka dari negara mana pun dan tidak pernah meminta login. Harga berasal dari umpan Agmarknet Pemerintah India dan diperbarui sendiri setiap hari."),
 ("Harga dinyatakan dalam satuan apa?",
  "Semua harga dalam ₹ per kuintal. 1 kuintal = 100 kg = sekitar 220,5 pon. Jadi ₹2.400 per kuintal berarti ₹24 per kg."),
 ("Kapan harga diperbarui?",
  "Mandi berdagang dengan Waktu Standar India (IST) dan harga harian masuk antara siang dan sore. Jam di atas menunjukkan waktu India saat ini, jadi Anda tahu kapan waktu tepat menelepon ke rumah."),
 ("Apakah ini memberi saran untuk bertani di {c}?",
  "Tidak. Semua data di sini adalah data India — mandi India, distrik India, dan skema Pemerintah India. Untuk tanah, cuaca, atau tanaman di {c}, tanyakan ke dinas pertanian setempat di sana."),
 ("Apakah ada biaya?",
  "Tidak. Harga mandi, peta, informasi skema, dan panduan bertani — semuanya gratis."),
],
"ms": [
 ("Bolehkah saya melihat harga mandi India dari {c}?",
  "Boleh. KrashiMitra terbuka dari mana-mana negara dan tidak pernah meminta log masuk. Harga datang daripada suapan Agmarknet Kerajaan India dan dikemas kini sendiri setiap hari."),
 ("Harga dinyatakan dalam unit apa?",
  "Semua harga dalam ₹ sekuintal. 1 kuintal = 100 kg = kira-kira 220.5 paun. Jadi ₹2,400 sekuintal bermakna ₹24 sekilogram."),
 ("Bilakah harga dikemas kini?",
  "Mandi berdagang mengikut Waktu Piawai India (IST) dan harga harian masuk antara tengah hari dan petang. Jam di atas menunjukkan waktu India sekarang, supaya anda tahu bila sesuai menelefon ke rumah."),
 ("Adakah ini memberi nasihat untuk pertanian di {c}?",
  "Tidak. Semua data di sini adalah data India — mandi India, daerah India dan skim Kerajaan India. Untuk tanah, cuaca atau tanaman di {c}, tanyalah perkhidmatan pertanian tempatan di sana."),
 ("Adakah sebarang bayaran?",
  "Tiada. Harga mandi, peta, maklumat skim dan panduan pertanian — semuanya percuma."),
],
"de": [
 ("Kann ich Indiens Mandi-Preise aus {c} abrufen?",
  "Ja. KrashiMitra lässt sich aus jedem Land öffnen und verlangt nie ein Login. Die Preise stammen aus dem Agmarknet-Feed der indischen Regierung und aktualisieren sich täglich von selbst."),
 ("In welcher Einheit stehen die Preise?",
  "Alle Preise sind in ₹ pro Quintal. 1 Quintal = 100 kg = rund 220,5 Pfund. ₹2.400 pro Quintal sind also ₹24 pro Kilo."),
 ("Wann werden die Preise aktualisiert?",
  "Mandis handeln nach indischer Standardzeit (IST), die Tagespreise treffen zwischen Nachmittag und Abend ein. Die Uhr oben zeigt die aktuelle Zeit in Indien, damit Sie wissen, wann Sie zu Hause anrufen können."),
 ("Gibt dies Ratschläge für die Landwirtschaft in {c}?",
  "Nein. Alle Daten hier sind indisch — indische Mandis, indische Distrikte und Programme der indischen Regierung. Für Boden, Wetter oder Kulturen in {c} fragen Sie den örtlichen landwirtschaftlichen Beratungsdienst."),
 ("Fallen Gebühren an?",
  "Nein. Mandi-Preise, Karten, Programminformationen und Anbau-Leitfäden sind alle kostenlos."),
],
}


# ── Titles, descriptions and H1s ─────────────────────────────
# Titles are written to the SERP budget this codebase already enforces:
# <= 68 characters, no brand suffix. `_fit` takes the first variant that
# fits, longest first — a single f-string cannot be safe here, because the
# same sentence is 46 characters for क़तर and 70 for the United Kingdom.
# A test checks every country's default language against both budgets.
TITLE_VARIANTS = {
 "en": ["India Mandi Bhav, District Maps & Kisan Yojana from {c}",
        "India Mandi Bhav, Maps & Kisan Yojana from {c}",
        "India Mandi Bhav & Kisan Yojana from {c}",
        "India Mandi Bhav from {c}"],
 "hi": ["{c} से भारत का मंडी भाव, नक्शा और किसान योजना",
        "{c} से भारत का मंडी भाव और किसान योजना",
        "{c} से भारत का मंडी भाव"],
 "ne": ["{c}बाट भारतको मण्डी भाउ, नक्सा र किसान योजना",
        "{c}बाट भारतको मण्डी भाउ र किसान योजना",
        "{c}बाट भारतको मण्डी भाउ"],
 "bn": ["{c} থেকে ভারতের মান্ডি দাম, জেলা মানচিত্র ও কিষান যোজনা",
        "{c} থেকে ভারতের মান্ডি দাম ও কিষান যোজনা",
        "{c} থেকে ভারতের মান্ডি দাম"],
 "si": ["{c} සිට ඉන්දියාවේ මණ්ඩි මිල, සිතියම් සහ කිසාන් යෝජනා",
        "{c} සිට ඉන්දියාවේ මණ්ඩි මිල සහ කිසාන් යෝජනා",
        "{c} සිට ඉන්දියාවේ මණ්ඩි මිල"],
 "ta": ["{c} இருந்து இந்திய மண்டி விலை, வரைபடம், கிசான் திட்டம்",
        "{c} இருந்து இந்திய மண்டி விலை, கிசான் திட்டம்",
        "{c} இருந்து இந்திய மண்டி விலை"],
 "ar": ["أسعار المندي الهندية وخرائط المقاطعات وبرامج الفلاحين من {c}",
        "أسعار المندي الهندية وخرائط المقاطعات من {c}",
        "أسعار المندي الهندية من {c}"],
 "id": ["Harga Mandi India, Peta Distrik & Skema Petani dari {c}",
        "Harga Mandi India & Skema Petani dari {c}",
        "Harga Mandi India dari {c}"],
 "ms": ["Harga Mandi India, Peta Daerah & Skim Petani dari {c}",
        "Harga Mandi India & Skim Petani dari {c}",
        "Harga Mandi India dari {c}"],
 "de": ["Indiens Mandi-Preise, Distriktkarten & Kisan Yojana aus {c}",
        "Indiens Mandi-Preise & Kisan Yojana aus {c}",
        "Indiens Mandi-Preise aus {c}"],
}

DESC_VARIANTS = {
 "en": ["Check India's mandi prices, district maps and kisan yojana from {c}. Daily rates from 650+ Indian mandis. Free, no login.",
        "India's mandi prices, district maps and kisan yojana from {c}. 650+ mandis, daily, free."],
 "hi": ["{c} में रहते हुए भारत की मंडी का आज का भाव, जिलों के नक्शे और सरकारी किसान योजनाएँ देखें। 650+ मंडियों का डेटा, रोज़ अपडेट, मुफ़्त।",
        "{c} से भारत का आज का मंडी भाव, जिलों के नक्शे और किसान योजनाएँ। 650+ मंडियाँ, रोज़ अपडेट, मुफ़्त।"],
 "ne": ["{c}मा बसेर भारतको आजको मण्डी भाउ, जिल्लाको नक्सा र सरकारी किसान योजना हेर्नुहोस्। ६५०+ मण्डीको डेटा, दैनिक अपडेट, नि:शुल्क।",
        "{c}बाट भारतको आजको मण्डी भाउ, नक्सा र किसान योजना। ६५०+ मण्डी, दैनिक अपडेट, नि:शुल्क।"],
 "bn": ["{c} থেকে ভারতের আজকের মান্ডি দাম, জেলার মানচিত্র ও সরকারি কিষান যোজনা দেখুন। ৬৫০+ মান্ডির তথ্য, প্রতিদিন আপডেট, বিনামূল্যে।",
        "{c} থেকে ভারতের মান্ডি দাম, মানচিত্র ও কিষান যোজনা। ৬৫০+ মান্ডি, প্রতিদিন আপডেট, ফ্রি।"],
 "si": ["{c} සිට ඉන්දියාවේ අද මණ්ඩි මිල, දිස්ත්‍රික් සිතියම් සහ රජයේ ගොවි වැඩසටහන් බලන්න. මණ්ඩි 650+ දත්ත, දිනපතා යාවත්කාලීන, නොමිලේ.",
        "{c} සිට ඉන්දියාවේ මණ්ඩි මිල, සිතියම් සහ ගොවි වැඩසටහන්. මණ්ඩි 650+, දිනපතා, නොමිලේ."],
 "ta": ["{c} இருந்து இந்தியாவின் இன்றைய மண்டி விலை, மாவட்ட வரைபடம், அரசுத் திட்டங்களைப் பாருங்கள். 650+ மண்டி தரவு, தினசரி புதுப்பிப்பு, இலவசம்.",
        "{c} இருந்து இந்திய மண்டி விலை, வரைபடம், கிசான் திட்டம். 650+ மண்டி, தினசரி, இலவசம்."],
 "ar": ["تابع أسعار المندي الهندية اليومية وخرائط المقاطعات وبرامج الفلاحين الحكومية من {c}. بيانات أكثر من 650 سوقاً، تحديث يومي، مجاناً.",
        "أسعار المندي الهندية وخرائط المقاطعات وبرامج الفلاحين من {c}. 650+ سوقاً، يومياً، مجاناً."],
 "id": ["Lihat harga mandi India hari ini, peta distrik, dan skema petani pemerintah dari {c}. Data 650+ mandi, diperbarui harian, gratis.",
        "Harga mandi India, peta distrik, dan skema petani dari {c}. 650+ mandi, harian, gratis."],
 "ms": ["Lihat harga mandi India hari ini, peta daerah dan skim petani kerajaan dari {c}. Data 650+ mandi, dikemas kini harian, percuma.",
        "Harga mandi India, peta daerah dan skim petani dari {c}. 650+ mandi, harian, percuma."],
 "de": ["Indiens tagesaktuelle Mandi-Preise, Distriktkarten und Kisan-Yojana-Programme aus {c}. Daten aus 650+ Mandis, täglich, kostenlos.",
        "Indiens Mandi-Preise, Distriktkarten und Kisan Yojana aus {c}. 650+ Mandis, täglich, kostenlos."],
}

# No flag emoji in the H1. Windows does not render regional-indicator pairs
# as flags, so "🇦🇪" arrives as a literal "AE" glued to the front of the
# headline — and desktop Windows is 97% of the traffic these pages get. The
# flag stays in the badge and the country chips, where a bare country code
# still reads correctly.
H1_VARIANTS = {
 "en": "India's mandi rates, maps and schemes — from {c}",
 "hi": "{c} से — भारत की मंडी, नक्शा और योजना",
 "ne": "{c}बाट — भारतको मण्डी, नक्सा र योजना",
 "bn": "{c} থেকে — ভারতের মান্ডি, মানচিত্র ও যোজনা",
 "si": "{c} සිට — ඉන්දියාවේ මණ්ඩි, සිතියම් සහ යෝජනා",
 "ta": "{c} இருந்து — இந்திய மண்டி, வரைபடம், திட்டங்கள்",
 "ar": "من {c} — أسواق الهند وخرائطها وبرامجها",
 "id": "Dari {c} — mandi, peta, dan skema India",
 "ms": "Dari {c} — mandi, peta dan skim India",
 "de": "Aus {c} — Indiens Mandis, Karten und Programme",
}
# ── Copy helpers ─────────────────────────────────────────────


def _fit(variants: list, limit: int = TITLE_MAX) -> str:
    """First variant that fits the budget, longest first.

    A single f-string cannot be safe here: the same sentence is 46 characters
    for क़तर and 70 for the United Kingdom, and the one that overflows gets
    truncated by Google mid-phrase. Same approach /bhav's titles use.
    """
    for v in variants:
        if len(v) <= limit:
            return v
    return variants[-1][:limit].rstrip(" ,-&،")


def t(key: str, lang: str, **fmt) -> str:
    """One UI string in `lang`, falling back to English."""
    e = T[key]
    return (e.get(lang) or e["en"]).format(**fmt)


def title_of(c, lang=None) -> str:
    lang = lang or c.lang
    return _fit([v.format(c=c.name(lang)) for v in TITLE_VARIANTS[lang]])


def desc_of(c, lang=None) -> str:
    lang = lang or c.lang
    return _fit([v.format(c=c.name(lang)) for v in DESC_VARIANTS[lang]], DESC_MAX)


def h1_of(c, lang=None) -> str:
    lang = lang or c.lang
    return H1_VARIANTS[lang].format(c=c.name(lang))


def faqs_of(c, lang=None) -> list:
    lang = lang or c.lang
    n = c.name(lang)
    return [(q.format(c=n), a.format(c=n)) for q, a in FAQ.get(lang, FAQ["en"])]


class Country:
    """One country page.

    `langs` is the toggle, in order, and langs[0] is what the page ships as:
    the <title>, the <meta description>, the <h1>, `<html lang>` and every
    visible string are rendered in it, and it is the only one a crawler
    sees. The rest are carried as a JSON blob the toggle swaps in — the same
    index-neutral trick free_month.card() uses, so adding a language never
    adds a URL (see the index-bloat note in the header).

    English is on every page because it is the one language every one of
    these audiences shares, and Hindi is on every page because it is the
    language the destination pages are written in and the language the
    Search Console log says these visitors are actually typing.

    `seen` is that country's own most-viewed pages from Search Console; it
    is what makes each page distinct, and it is allowed to fall back to the
    shared set for a country that has never sent a measurable visit
    (Nigeria: 3 impressions in 90 days).

    `name_loc` only needs the country's own languages — hi and en come from
    name_hi/name_en, and no other language is ever used by two countries
    except Arabic, which is why the five Gulf rows each carry their own.
    """

    def __init__(self, code, name_en, name_hi, flag, langs, currency,
                 seen=(), name_loc=None, note=None, short_en=""):
        self.code, self.name_en, self.name_hi = code, name_en, name_hi
        self.flag, self.langs, self.currency = flag, list(langs), currency
        self.seen = list(seen)
        self.name_loc = dict(name_loc or {})
        self.note = dict(note or {})
        # How the country is written in a search box, which is not always its
        # formal name — nobody types "United States of America" and the title
        # budget cannot afford it either.
        self.short_en = short_en or name_en

    @property
    def lang(self):
        """The language the page ships in."""
        return self.langs[0]

    @property
    def script(self):
        """Kept for readability in the tests: the script the title is in."""
        return "latin" if SCRIPT_RANGE[self.lang] is None else self.lang

    def name(self, lang):
        """The country's name written in `lang`."""
        if lang in self.name_loc:
            return self.name_loc[lang]
        if lang == "hi":
            return self.name_hi
        return self.short_en

    @property
    def url(self):
        return f"{SITE}/{self.code}"


# ── The countries ────────────────────────────────────────────
# The seven that already had a page keep their URL. The seven added in the
# 2026-09-10 rewrite are the ones the data asked for: the five Gulf states
# (1,308 impressions and 15 of our 24 international clicks), plus Canada and
# Germany, both of which search "sarkari kisan yojana" and land on
# /sarkari_yojana. Nothing was added speculatively — Australia (14
# impressions) and Singapore (12) still have no page, and should not.
#
# `langs` is the country's own official language(s) first, then English,
# then Hindi. Sri Lanka has two official languages and gets both, which is
# the rule the rest of the table follows rather than an exception to it.
COUNTRIES = [
    Country("us", "United States", "अमेरिका", "🇺🇸", ["en", "hi"], "US Dollar (USD)",
            ["/sarkari_yojana", "/articles/ganna-rog", "/bhav/paddy-common", "/bhav"],
            note={"hi": "अमेरिका से सबसे ज़्यादा खोजी जाने वाली चीज़ सरकारी किसान योजनाएँ हैं।",
                  "en": "Government farm schemes are what visitors from the US look for most."},
            short_en="the USA"),
    Country("uk", "United Kingdom", "ब्रिटेन", "🇬🇧", ["en", "hi"], "Pound Sterling (GBP)",
            ["/sarkari_yojana", "/naksha/uttar-pradesh/jile", "/articles/urea-guide-up", "/bhav"],
            note={"hi": "ब्रिटेन से आने वाले ज़्यादातर लोग योजनाएँ और जिलों के नक्शे देखते हैं।",
                  "en": "Visitors from the UK mostly look up schemes and district maps."},
            short_en="the UK"),
    Country("ae", "United Arab Emirates", "संयुक्त अरब अमीरात", "🇦🇪",
            ["ar", "en", "hi"], "UAE Dirham (AED)",
            ["/bhav/wheat", "/bhav/onion", "/naksha/rajasthan/jile", "/articles/urea-guide-up"],
            name_loc={"ar": "الإمارات"},
            note={"hi": "यूएई से गेहूं और प्याज़ का भाव और राजस्थान–यूपी के नक्शे सबसे ज़्यादा देखे जाते हैं।",
                  "en": "From the UAE, wheat and onion rates and Rajasthan/UP maps are viewed most.",
                  "ar": "من الإمارات، أكثر ما يُطالَع هو أسعار القمح والبصل وخرائط راجستان وأوتار براديش."},
            short_en="the UAE"),
    Country("sa", "Saudi Arabia", "सऊदी अरब", "🇸🇦", ["ar", "en", "hi"], "Saudi Riyal (SAR)",
            ["/sarkari_yojana", "/bhav/green-peas", "/bhav/potato", "/articles/urea-guide-up"],
            name_loc={"ar": "السعودية"},
            note={"hi": "सऊदी अरब से आने वाले ज़्यादातर लोग सरकारी योजनाएँ खोजते हैं।",
                  "en": "Most visitors from Saudi Arabia are searching for government schemes.",
                  "ar": "معظم الزوار من السعودية يبحثون عن البرامج الحكومية."}),
    Country("kw", "Kuwait", "कुवैत", "🇰🇼", ["ar", "en", "hi"], "Kuwaiti Dinar (KWD)",
            ["/naksha/rajasthan/jile", "/naksha/rajasthan/nagaur", "/bhav/onion", "/articles/urea-guide-up"],
            name_loc={"ar": "الكويت"},
            note={"hi": "कुवैत से राजस्थान के जिलों और गाँवों की खोज सबसे ऊपर है।",
                  "en": "Rajasthan districts and villages top the list from Kuwait.",
                  "ar": "تتصدّر مقاطعات راجستان وقراها عمليات البحث القادمة من الكويت."}),
    Country("qa", "Qatar", "क़तर", "🇶🇦", ["ar", "en", "hi"], "Qatari Riyal (QAR)",
            ["/naksha/punjab", "/bhav/wheat", "/bhav/potato", "/articles/urea-guide-up"],
            name_loc={"ar": "قطر"},
            note={"hi": "क़तर से पंजाब–यूपी के नक्शे और गेहूं–धान का भाव देखा जाता है।",
                  "en": "Punjab and UP maps and wheat and paddy rates are what Qatar looks up.",
                  "ar": "من قطر تُطالَع خرائط البنجاب وأوتار براديش وأسعار القمح والأرز."}),
    Country("om", "Oman", "ओमान", "🇴🇲", ["ar", "en", "hi"], "Omani Rial (OMR)",
            ["/naksha/uttar-pradesh/kushinagar", "/naksha/jharkhand", "/bhav/paddy-common", "/bhav/wheat"],
            name_loc={"ar": "عُمان"},
            note={"hi": "ओमान से पूर्वी यूपी और बिहार–झारखंड के नक्शे सबसे ज़्यादा देखे जाते हैं।",
                  "en": "Eastern UP, Bihar and Jharkhand maps are viewed most from Oman.",
                  "ar": "أكثر ما يُطالَع من عُمان هو خرائط شرق أوتار براديش وبيهار وجهارخاند."}),
    Country("np", "Nepal", "नेपाल", "🇳🇵", ["ne", "en", "hi"], "Nepali Rupee (NPR)",
            ["/bhav/mentha-oil", "/bhav/maize", "/bhav/onion", "/articles/urea-guide-up"],
            name_loc={"ne": "नेपाल"},
            note={"hi": "नेपाल से मेंथा ऑयल, मक्का और प्याज़ के भाव और यूरिया की जानकारी सबसे ज़्यादा देखी जाती है।",
                  "en": "Mentha oil, maize and onion rates and urea guidance lead from Nepal.",
                  "ne": "नेपालबाट मेन्था तेल, मकै र प्याजको भाउ अनि युरियाको जानकारी सबैभन्दा बढी हेरिन्छ।"}),
    Country("bd", "Bangladesh", "बांग्लादेश", "🇧🇩", ["bn", "en", "hi"], "Bangladeshi Taka (BDT)",
            ["/naksha/bihar/bhagalpur", "/bhav/mustard", "/bhav", "/naksha/west-bengal/jile"],
            name_loc={"bn": "বাংলাদেশ"},
            note={"hi": "बांग्लादेश से बिहार और पश्चिम बंगाल के नक्शे और सरसों का भाव देखा जाता है।",
                  "en": "Bihar and West Bengal maps and mustard rates are what Bangladesh looks up.",
                  "bn": "বাংলাদেশ থেকে বিহার ও পশ্চিমবঙ্গের মানচিত্র আর সরিষার দাম সবচেয়ে বেশি দেখা হয়।"}),
    Country("ca", "Canada", "कनाडा", "🇨🇦", ["en", "hi"], "Canadian Dollar (CAD)",
            ["/sarkari_yojana", "/bhav", "/bhav/wheat", "/articles/urea-guide-up"],
            note={"hi": "कनाडा से सरकारी योजनाएँ और मंडी भाव सबसे ज़्यादा खोजे जाते हैं।",
                  "en": "Schemes and mandi prices lead the searches from Canada."}),
    Country("de", "Germany", "जर्मनी", "🇩🇪", ["de", "en", "hi"], "Euro (EUR)",
            ["/sarkari_yojana", "/naksha", "/articles/urea-guide-up", "/bhav"],
            name_loc={"de": "Deutschland"},
            note={"hi": "जर्मनी से लगभग हर विज़िट सरकारी किसान योजनाओं की खोज से आती है।",
                  "en": "Almost every visit from Germany arrives searching for kisan schemes.",
                  "de": "Fast jeder Besuch aus Deutschland kommt über die Suche nach Kisan-Programmen."}),
    Country("my", "Malaysia", "मलेशिया", "🇲🇾", ["ms", "en", "hi"], "Malaysian Ringgit (MYR)",
            ["/bhav/wheat", "/articles/urea-guide-up", "/naksha/uttar-pradesh/jile", "/articles/dap-guide-up"],
            name_loc={"ms": "Malaysia"},
            note={"hi": "मलेशिया से यूपी की मंडियों के भाव और खाद की जानकारी देखी जाती है।",
                  "en": "UP mandi rates and fertiliser guidance are what Malaysia reads.",
                  "ms": "Harga mandi UP dan panduan baja ialah apa yang paling banyak dibaca dari Malaysia."}),
    Country("id", "Indonesia", "इंडोनेशिया", "🇮🇩", ["id", "en", "hi"], "Indonesian Rupiah (IDR)",
            ["/naksha", "/bhav", "/articles/urea-guide-up", "/articles/"],
            name_loc={"id": "Indonesia"},
            note={"hi": "इंडोनेशिया से आने वाली खोजें ज़्यादातर भारत के जिलों के नक्शों की होती हैं।",
                  "en": "Searches from Indonesia are mostly for Indian district maps.",
                  "id": "Pencarian dari Indonesia sebagian besar adalah peta distrik India."}),
    Country("ng", "Nigeria", "नाइजीरिया", "🇳🇬", ["en", "hi"], "Nigerian Naira (NGN)",
            ["/naksha", "/bhav", "/sarkari_yojana", "/articles/"]),
    Country("lk", "Sri Lanka", "श्रीलंका", "🇱🇰", ["si", "ta", "en", "hi"], "Sri Lankan Rupee (LKR)",
            ["/bhav", "/naksha", "/articles/urea-guide-up", "/sarkari_yojana"],
            name_loc={"si": "ශ්‍රී ලංකාව", "ta": "இலங்கை"}),
]
CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--km-cream,#f5f7f4);color:var(--km-text-dark,#1a2e23);
  font-family:var(--km-font-body,'DM Sans','Noto Sans Devanagari',sans-serif);
  -webkit-font-smoothing:antialiased}
.iw{max-width:1100px;margin:0 auto;padding:0 18px}
.ihero{background:linear-gradient(160deg,#1a3c2e 0%,#2d6a4f 60%,#35795a 100%);
  color:#fff;padding:38px 0 34px;margin-top:0}
.ihero h1{font-family:var(--km-font-serif,'Noto Serif Devanagari',serif);
  font-size:27px;line-height:1.28;margin:0 0 12px;font-weight:800}
.ihero p{margin:0;font-size:15.5px;line-height:1.68;color:#dbeee2;max-width:62ch}
.ibadge{display:inline-block;background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.22);
  color:#d8f3dc;font-size:12px;font-weight:700;padding:5px 12px;border-radius:999px;margin-bottom:14px}
.istats{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}
.istat{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.16);
  border-radius:12px;padding:10px 14px;min-width:96px}
.istat b{display:block;font-size:19px;font-weight:800;color:#fff}
.istat span{font-size:11.5px;color:#c6e3d2}
.iclock{background:#fff;border:1px solid var(--km-border,#e5e9e6);border-radius:14px;
  padding:14px 16px;margin:-22px 0 0;position:relative;box-shadow:0 6px 22px rgba(26,60,46,.09);
  display:flex;flex-wrap:wrap;gap:14px;align-items:center}
.iclock .ct{flex:1 1 130px;min-width:130px}
.iclock .cl{font-size:11.5px;color:var(--km-text-soft,#7c8983);font-weight:700;
  text-transform:uppercase;letter-spacing:.4px}
.iclock .cv{font-size:20px;font-weight:800;font-variant-numeric:tabular-nums;
  color:var(--km-green-dark,#1a3c2e)}
.iclock .cn{flex:2 1 240px;font-size:12.5px;color:var(--km-text-mid,#4a5a52);line-height:1.55}
section.isec{padding:34px 0 6px}
.ih2{font-family:var(--km-font-serif,serif);font-size:20px;font-weight:800;margin:0 0 4px}
.isub{font-size:13.5px;color:var(--km-text-mid,#4a5a52);margin:0 0 16px;line-height:1.6}
.igrid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:620px){.igrid{grid-template-columns:1fr 1fr}
  .ihero h1{font-size:34px}.iw{padding:0 24px}}
@media(min-width:900px){.igrid.three{grid-template-columns:1fr 1fr 1fr}}
.icard{display:block;background:#fff;border:1px solid var(--km-border,#e5e9e6);
  border-radius:14px;padding:16px 17px;text-decoration:none;color:inherit;
  transition:border-color .16s,transform .16s,box-shadow .16s}
.icard:hover{border-color:var(--km-green-light,#52b788);transform:translateY(-2px);
  box-shadow:0 8px 24px rgba(26,60,46,.08)}
.icard b{display:block;font-size:16px;font-weight:700;color:var(--km-green-dark,#1a3c2e);
  margin-bottom:4px}
.icard span{font-size:13px;color:var(--km-text-mid,#4a5a52);line-height:1.55}
.ichips{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
.ichip{background:#fff;border:1px solid var(--km-border,#e5e9e6);border-radius:999px;
  padding:8px 14px;font-size:13.5px;font-weight:600;text-decoration:none;
  color:var(--km-green-dark,#1a3c2e)}
.ichip:hover{border-color:var(--km-green-light,#52b788);background:var(--km-green-pale,#d8f3dc)}
.inote{background:#fff;border:1px solid var(--km-border,#e5e9e6);border-left:4px solid var(--km-amber,#e9a825);
  border-radius:12px;padding:15px 17px;font-size:14px;line-height:1.7;color:var(--km-text-mid,#4a5a52)}
.inote b{color:var(--km-text-dark,#1a2e23)}
.ifaq{background:#fff;border:1px solid var(--km-border,#e5e9e6);border-radius:12px;
  padding:15px 17px;margin-bottom:10px}
.ifaq h3{margin:0 0 6px;font-size:15px;font-weight:700;color:var(--km-green-dark,#1a3c2e)}
.ifaq p{margin:0;font-size:14px;line-height:1.7;color:var(--km-text-mid,#4a5a52)}
.iflags{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.iflag{background:#fff;border:1px solid var(--km-border,#e5e9e6);border-radius:10px;
  padding:8px 12px;font-size:13.5px;text-decoration:none;color:var(--km-text-dark,#1a2e23);font-weight:600}
.iflag:hover{border-color:var(--km-green-light,#52b788)}
.iend{margin:34px 0 44px;padding:22px 18px;background:var(--km-green-dark,#1a3c2e);
  border-radius:16px;color:#fff;text-align:center}
.iend h2{font-family:var(--km-font-serif,serif);font-size:20px;margin:0 0 8px}
.iend p{margin:0 0 16px;font-size:14px;color:#c6e3d2;line-height:1.6}
.ibtn{display:inline-block;background:var(--km-amber,#e9a825);color:#1a2e1e;font-weight:800;
  text-decoration:none;padding:12px 26px;border-radius:999px;font-size:15px}
"""

CLOCK_JS = """
(function(){
  // Two live clocks: India, and wherever the reader is. The IST one is read
  // from the browser with an explicit Asia/Kolkata timezone rather than a
  // hard-coded +5:30 offset, so it stays right without anything to maintain.
  // If Intl is missing or throws, the strip removes itself rather than
  // showing a wrong time — a wrong clock is worse than no clock.
  var box = document.getElementById('km-clock');
  if (!box) return;
  function fmt(tz){
    try { return new Intl.DateTimeFormat('en-GB', {hour:'2-digit', minute:'2-digit',
      hour12:false, timeZone:tz}).format(new Date()); }
    catch(e){ return null; }
  }
  function tick(){
    var ist = fmt('Asia/Kolkata'), here = fmt(undefined);
    if (!ist || !here){ box.remove(); return; }
    document.getElementById('km-ist').textContent = ist;
    document.getElementById('km-here').textContent = here;
  }
  tick();
  setInterval(tick, 30000);
})();
"""

LANG_CSS = """
.ilang{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 16px}
.ilang-l{font-size:11px;font-weight:700;color:#a7cbb8;text-transform:uppercase;letter-spacing:.5px}
.ilang-b{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.24);color:#eaf6ee;
  font-family:inherit;font-size:13px;font-weight:700;padding:6px 14px;border-radius:999px;
  cursor:pointer;line-height:1.4}
.ilang-b:hover{background:rgba(255,255,255,.2)}
.ilang-b.active{background:#fff;color:#1a3c2e;border-color:#fff}
[dir=rtl] .inote{border-left:none;border-right:4px solid var(--km-amber,#e9a825)}
[dir=rtl] .iclock .cn{text-align:right}
"""

# The toggle. Buttons, never links: an <a href="?lang=ar"> would be a
# crawlable URL and would multiply this page by its language count in the
# index, which is the thing free_month.card() and index-bloat-prune already
# decided against. The page ships in langs[0]; every other language lives in
# a JSON island and is swapped into the DOM in place, so there is exactly one
# URL no matter how many languages a country gets.
#
# The default language is NOT duplicated into the island — switching back to
# it restores each element from the markup it shipped with, which also means
# a crawler and a JS-off phone see the native page byte-for-byte.
LANG_JS = """
(function(){
  var el = document.getElementById('km-i18n');
  if (!el) return;
  var CFG;
  try { CFG = JSON.parse(el.textContent); } catch(e){ return; }
  var root = document.getElementById('km-i18n-root');
  var pick = document.getElementById('km-lang-pick');
  if (!root || !pick) return;

  function nodes(){ return document.querySelectorAll('[data-i18n]'); }

  function apply(lang){
    if (CFG.langs.indexOf(lang) < 0) return;
    var tbl = CFG.s[lang] || null;   // null for the default: restore instead
    [].forEach.call(nodes(), function(n){
      if (n.getAttribute('data-i18n-o') === null || n.getAttribute('data-i18n-o') === undefined) {
        n.setAttribute('data-i18n-o', n.innerHTML);
      }
      var k = n.getAttribute('data-i18n');
      var v = tbl ? tbl[k] : n.getAttribute('data-i18n-o');
      if (v !== undefined && v !== null) n.innerHTML = v;
    });
    var meta = CFG.meta[lang] || {};
    root.setAttribute('dir', meta.dir || 'ltr');
    document.documentElement.setAttribute('lang', meta.html || lang);
    if (meta.title) document.title = meta.title;
    else if (CFG.meta[CFG.def] && lang === CFG.def && CFG.meta[CFG.def].title)
      document.title = CFG.meta[CFG.def].title;
    [].forEach.call(pick.querySelectorAll('[data-lang]'), function(b){
      b.classList.toggle('active', b.getAttribute('data-lang') === lang);
    });
    try { localStorage.setItem('km_intl_lang', lang); } catch(e){}
  }

  [].forEach.call(pick.querySelectorAll('[data-lang]'), function(b){
    b.addEventListener('click', function(){ apply(b.getAttribute('data-lang')); });
  });

  // What the reader chose on this page wins. Failing that, the site-wide
  // picker's choice is honoured when this page offers that language, so a
  // reader who set English in the drawer does not land back in Nepali.
  var want = null;
  try { want = localStorage.getItem('km_intl_lang'); } catch(e){}
  if (!want || CFG.langs.indexOf(want) < 0) {
    try { want = localStorage.getItem('km_lang'); } catch(e){}
  }
  if (want && want !== CFG.def && CFG.langs.indexOf(want) >= 0) apply(want);
})();
"""


def _lang_picker(langs: list, lang: str) -> str:
    """The visible toggle. langs[0] is the country's own language."""
    btns = "".join(
        f'<button type="button" class="ilang-b{" active" if l == lang else ""}" '
        f'data-lang="{l}">{escape(LANGS[l]["name"])}</button>' for l in langs)
    return (f'<div class="ilang" id="km-lang-pick">'
            f'<span class="ilang-l" data-i18n="lang_label">{escape(t("lang_label", lang))}</span>'
            f'{btns}</div>')


def _fonts(langs: list):
    """(google-fonts query fragment, extra CSS font-family names) for the
    scripts this page can render. Latin and Devanagari are always loaded."""
    fams, names = [], []
    for l in langs:
        f = LANGS[l]["font"]
        if f and f[0] not in fams:
            fams.append(f[0])
            names.append(f[1])
    q = "".join(f"&family={f}" for f in fams)
    css = ""
    if names:
        stack = ",".join(f"'{n}'" for n in names)
        css = (f"\n#km-i18n-root{{font-family:'DM Sans','Noto Sans Devanagari',{stack},sans-serif}}"
               f"\n#km-i18n-root .ihero h1,#km-i18n-root .ih2,#km-i18n-root .iend h2"
               f"{{font-family:'Noto Serif Devanagari','DM Sans',{stack},serif}}\n")
    return q, css
# ── The site chrome ──────────────────────────────────────────
# The same header/drawer/footer every static page ships, with two deliberate
# differences.
#
# Every href is ABSOLUTE. help.html and friends link "weather.html" relative
# to the site root, which is fine for a file at the root — but these pages
# live at /international/us.html and are SERVED at /us, so a relative link
# would resolve to /international/weather.html and 404.
#
# And every nav label is rendered from LABELS in the page's language, so a
# reader on /np sees the bar in Nepali rather than a Hindi bar bolted to a
# Nepali page. The destinations are still Hindi pages — which is why the
# CARDS below keep the Hindi original on their second line.
#
# The drawer's LINKS are not written here. drawer-menu.js clears
# .sidebar-drawer-links and rebuilds it from its own GROUPS table at runtime,
# and it owns the drawer title too, so per-page drawer markup would be dead
# weight that silently goes stale — only the skeleton it fills is needed.


def _nav(url: str, lang: str, cls: str) -> str:
    return (f'<a class="{cls}" href="{url}" data-i18n="l:{url}">'
            f'{escape(label(url, lang))}</a>')


def header(lang: str) -> str:
    top = "<span class=\"top-utility-divider\">|</span>".join(
        _nav(u, lang, "top-utility-link")
        for u in ("/", "/naksha", "/articles/", "/sarkari_yojana"))
    nav = "".join(_nav(u, lang, "header-nav-link")
                  for u in ("/bhav", "/naksha", "/sarkari_yojana", "/articles/"))
    cnav = "".join(_nav(u, lang, "cnav-item")
                   for u in ("/bhav", "/naksha", "/sarkari_yojana", "/articles/", "/krashi_news"))
    return f"""
<div class="header-wrapper" id="header-wrapper">
<div class="pre-topbar">
  <a href="mailto:krashimitra038@gmail.com" class="pre-topbar-helpline"
     data-i18n="email_line">{escape(t("email_line", lang))}</a>
</div>
<div class="top-utility-bar"><div class="top-utility-inner">
  <div class="top-utility-left">{top}</div>
  <div class="top-utility-right">
    <a href="/international" class="top-utility-link">🌍 International</a>
  </div>
</div></div>
<header class="main-header"><div class="main-header-inner">
  <button class="hamburger-btn" onclick="document.getElementById('km-drawer').classList.add('open')" aria-label="Menu">☰</button>
  <div class="header-left-group">
    <a class="header-logo-link" href="/">
      <img src="/assets/krashimitra_logo.png" alt="कृषि मित्र" class="header-logo-circle" width="38" height="38">
      <span class="header-logo-text">कृषि मित्र</span></a>
  </div>
  <nav class="header-nav">{nav}</nav>
  <div class="header-right-group">
    <a href="/login" class="header-avatar-btn" id="header-avatar-btn">👤</a>
  </div>
</div></header>
<div class="commodity-navbar"><div class="cnav-inner">{cnav}</div></div>
</div><!-- /.header-wrapper -->
<div class="sidebar-drawer-overlay" id="km-drawer" onclick="this.classList.remove('open')">
  <div class="sidebar-drawer" onclick="event.stopPropagation()">
    <div class="sidebar-drawer-header"><span class="sidebar-drawer-title">मेनु</span>
      <button class="sidebar-drawer-close" onclick="document.getElementById('km-drawer').classList.remove('open')" aria-label="Close menu">✕</button></div>
    <div class="sidebar-drawer-links"></div>
  </div>
</div>
<div class="topbar-spacer" id="topbar-spacer"></div>
"""


def footer(lang: str) -> str:
    nav = "".join(_nav(u, lang, "")
                  for u in ("/", "/bhav", "/naksha", "/sarkari_yojana"))
    tail = "".join(_nav(u, lang, "") for u in ("/about", "/privacy-policy"))
    return f"""
<footer class="km-footer"><div class="km-footer-inner">
  <div class="km-footer-brand">🌾 कृषि मित्र</div>
  <nav class="km-footer-nav">{nav}
    <a href="/international">🌍 International</a>{tail}
  </nav>
  <div class="km-footer-note" data-i18n="footer_note">{escape(t("footer_note", lang))}</div>
</div></footer>
"""


# ── Card and chip helpers ────────────────────────────────────
# The second line of a card is always the OTHER of the pair the reader needs:
# on a Hindi page it is the English gloss, and on every other page it is the
# Hindi original — because the destination page is written in Hindi, and
# because it keeps the Hindi phrases these countries actually type ("मेंथा
# ऑयल भाव", "गेहूं का रेट") in the indexed markup instead of translating
# them out of it.
def _sub(url: str, lang: str) -> str:
    return label(url, "en" if lang == "hi" else "hi")


def _cards(urls, lang, three=False) -> str:
    cls = "igrid three" if three else "igrid"
    out = []
    for u in urls:
        out.append(
            f'<a class="icard" href="{u}">'
            f'<b data-i18n="l:{u}">{escape(label(u, lang))}</b>'
            f'<span data-i18n="s:{u}">{escape(_sub(u, lang))}</span></a>')
    return f'<div class="{cls}">' + "".join(out) + "</div>"


def _chips(urls, lang) -> str:
    return '<div class="ichips">' + "".join(
        f'<a class="ichip" href="{u}" data-i18n="l:{u}">{escape(label(u, lang))}</a>'
        for u in urls) + "</div>"


MAP_CHIPS = ["/naksha", "/naksha/uttar-pradesh/jile", "/naksha/rajasthan/jile",
             "/naksha/west-bengal/jile", "/naksha/punjab"]
NAV_URLS = ["/", "/bhav", "/naksha", "/sarkari_yojana", "/articles/",
            "/krashi_news", "/about", "/privacy-policy"]


def page_strings(c, lang: str) -> dict:
    """Every swappable string on `c`'s page, in `lang`, ready for innerHTML."""
    s = {}
    for k in T:
        v = t(k, lang, c=c.name(lang), cur=c.currency)
        s[k] = v if k in RICH else escape(v)
    for u in dict.fromkeys(NAV_URLS + CORE + CROPS + READS + MAP_CHIPS + (c.seen or [])):
        s["l:" + u] = escape(label(u, lang))
        s["s:" + u] = escape(_sub(u, lang))
    s["h1"] = escape(h1_of(c, lang))
    if c.note:
        s["note"] = escape(c.note.get(lang) or c.note.get("en") or c.note["hi"])
    for i, (q, a) in enumerate(faqs_of(c, lang)):
        s[f"fq{i}"] = escape(q)
        s[f"fa{i}"] = escape(a)
    return s


def _island(c) -> str:
    """The JSON the toggle reads. The default language is left out — the
    page already carries it as markup, and apply() restores from that."""
    blob = {
        "def": c.lang,
        "langs": c.langs,
        "meta": {l: {"dir": LANGS[l]["dir"], "html": l, "title": title_of(c, l)}
                 for l in c.langs},
        "s": {l: page_strings(c, l) for l in c.langs if l != c.lang},
    }
    return json.dumps(blob, ensure_ascii=False).replace("</", "<\\/")
def render(c) -> str:
    lang = c.lang
    title, desc = title_of(c), desc_of(c)
    faqs = faqs_of(c)
    faq_html = "".join(
        f'<div class="ifaq"><h3 data-i18n="fq{i}">{escape(q)}</h3>'
        f'<p data-i18n="fa{i}">{escape(a)}</p></div>'
        for i, (q, a) in enumerate(faqs))

    ld = [
        {"@context": "https://schema.org", "@type": "WebPage",
         "@id": c.url + "#page", "url": c.url, "name": title, "description": desc,
         "inLanguage": lang, "isPartOf": {"@type": "WebSite", "name": "KrashiMitra",
                                          "url": SITE},
         "about": {"@type": "Thing", "name": "Indian agricultural market prices"},
         "publisher": {"@type": "Organization", "name": "KrashiMitra", "url": SITE,
                       "logo": f"{SITE}/assets/krashimitra_logo.png"}},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "KrashiMitra", "item": SITE},
             {"@type": "ListItem", "position": 2, "name": "International",
              "item": f"{SITE}/international"},
             {"@type": "ListItem", "position": 3, "name": c.name_en, "item": c.url}]},
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}}
                        for q, a in faqs]},
    ]
    ld_html = "\n".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in ld)

    others = "".join(
        f'<a class="iflag" href="/{o.code}">{o.flag} {escape(o.name_en)}</a>'
        for o in COUNTRIES if o.code != c.code)

    note = (f'<div class="inote" data-i18n="note">'
            f'{escape(c.note.get(lang) or c.note.get("en") or c.note["hi"])}</div>'
            if c.note else "")

    seen = c.seen or CORE + ["/articles/"]
    font_q, font_css = _fonts(c.langs)
    d = LANGS[lang]["dir"]

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="/analytics.js"></script>
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{c.url}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta property="og:type" content="website">
<meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:url" content="{c.url}">
<meta property="og:locale" content="{og_locale(lang, c.code)}">
{social_tags(title, desc)}
<link rel="icon" href="/assets/favicon.ico">
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/km-shell.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&family=Noto+Serif+Devanagari:wght@700;800{font_q}&display=swap" rel="stylesheet">
{ld_html}
<style>{CSS}{LANG_CSS}{font_css}</style>
</head>
<body>
{header(lang)}
<div id="km-i18n-root" dir="{d}">
<header class="ihero">
  <div class="iw">
    {_lang_picker(c.langs, lang)}
    <span class="ibadge">{escape(c.flag)} {escape(c.name_en)}</span>
    <h1 data-i18n="h1">{escape(h1_of(c))}</h1>
    <p data-i18n="hero_sub">{escape(t("hero_sub", lang))}</p>
    <div class="istats">
      <div class="istat"><b>650+</b><span data-i18n="stat_mandis">{escape(t("stat_mandis", lang))}</span></div>
      <div class="istat"><b>20+</b><span data-i18n="stat_states">{escape(t("stat_states", lang))}</span></div>
      <div class="istat"><b>150+</b><span data-i18n="stat_crops">{escape(t("stat_crops", lang))}</span></div>
      <div class="istat"><b>₹0</b><span data-i18n="stat_free">{escape(t("stat_free", lang))}</span></div>
    </div>
  </div>
</header>

<div class="iw">
  <div class="iclock" id="km-clock">
    <div class="ct"><div class="cl" data-i18n="clock_in">{escape(t("clock_in", lang))}</div><div class="cv" id="km-ist">--:--</div></div>
    <div class="ct"><div class="cl" data-i18n="clock_here">{escape(t("clock_here", lang))}</div><div class="cv" id="km-here">--:--</div></div>
    <div class="cn" data-i18n="clock_note">{escape(t("clock_note", lang))}</div>
  </div>
</div>

<main class="iw">

  <section class="isec">
    <h2 class="ih2" data-i18n="s_top_h">{escape(t("s_top_h", lang))}</h2>
    <p class="isub" data-i18n="s_top_sub">{escape(t("s_top_sub", lang))}</p>
    {_cards(CORE, lang, three=True)}
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="s_price_h">{escape(t("s_price_h", lang))}</h2>
    <p class="isub" data-i18n="s_price_sub">{escape(t("s_price_sub", lang))}</p>
    {_chips(CROPS, lang)}
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="s_unit_h">{escape(t("s_unit_h", lang))}</h2>
    <p class="isub" data-i18n="s_unit_sub">{escape(t("s_unit_sub", lang, c=c.name(lang)))}</p>
    <div class="inote">
      <span data-i18n="unit_note">{t("unit_note", lang)}</span>
      <br><span style="opacity:.75" data-i18n="unit_note2">{escape(t("unit_note2", lang, cur=c.currency))}</span>
    </div>
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="s_seen_h">{escape(t("s_seen_h", lang, c=c.name(lang)))}</h2>
    <p class="isub" data-i18n="s_seen_sub">{escape(t("s_seen_sub", lang, c=c.name(lang)))}</p>
    {note}
    <div style="height:12px"></div>
    {_cards(seen, lang)}
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="s_maps_h">{escape(t("s_maps_h", lang))}</h2>
    <p class="isub" data-i18n="s_maps_sub">{escape(t("s_maps_sub", lang))}</p>
    {_chips(MAP_CHIPS, lang)}
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="s_read_h">{escape(t("s_read_h", lang))}</h2>
    <p class="isub" data-i18n="s_read_sub">{escape(t("s_read_sub", lang))}</p>
    {_cards(READS, lang)}
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="s_faq_h">{escape(t("s_faq_h", lang))}</h2>
    {faq_html}
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="s_other_h">{escape(t("s_other_h", lang))}</h2>
    <p class="isub" data-i18n="s_other_sub">{escape(t("s_other_sub", lang))}</p>
    <div class="iflags"><a class="iflag" href="/international">🌍 <span data-i18n="all_countries">{escape(t("all_countries", lang))}</span></a>{others}</div>
  </section>

  <div class="iend">
    <h2 data-i18n="cta_h">{escape(t("cta_h", lang))}</h2>
    <p data-i18n="cta_p">{escape(t("cta_p", lang))}</p>
    <a class="ibtn" href="/bhav" data-i18n="cta_btn">{escape(t("cta_btn", lang))}</a>
  </div>

</main>
</div><!-- /#km-i18n-root -->

{footer(lang)}
<script type="application/json" id="km-i18n">{_island(c)}</script>
<script>{CLOCK_JS}</script>
<script>{LANG_JS}</script>
<script src="/header-scroll.js"></script>
<script src="/drawer-menu.js"></script>
<script src="/bottomnav.js" defer></script>
</body>
</html>
"""
# ── The hub ──────────────────────────────────────────────────
# /international is a directory, not a country, so it has no native language
# of its own. It ships in English — it is the page a reader lands on when
# they do not yet know which country page they want — with Hindi on the same
# toggle.
HUB_LANGS = ["en", "hi"]

HUB_T = {
"hub_h1": {
 "en": "India's mandi, from anywhere in the world",
 "hi": "भारत की मंडी, दुनिया में कहीं से भी"},
"hub_sub": {
 "en": "Your family farms in India and you are abroad — so check today's rate before they sell, open the district map, and see which government schemes are running. Every figure here is Indian, from the Government of India's Agmarknet feed.",
 "hi": "घर भारत में है और आप बाहर हैं — तो बिकवाली से पहले आज का भाव देख लीजिए, जिले का नक्शा खोलिए, और चल रही सरकारी योजनाएँ जान लीजिए। सारा डेटा भारत का है, भारत सरकार के Agmarknet फ़ीड से।"},
"hub_pick_h": {"en": "Pick your country", "hi": "अपना देश चुनिए"},
"hub_pick_sub": {
 "en": "Each page opens in that country's own language, with what visitors from there read most.",
 "hi": "हर पन्ना उस देश की अपनी भाषा में खुलता है, और वहीं से सबसे ज़्यादा पढ़ी जाने वाली चीज़ें दिखाता है।"},
"hub_direct_h": {"en": "Or go straight there", "hi": "सीधे यहाँ जाइए"},
"hub_direct_sub": {"en": "Straight to the thing you came for.",
                   "hi": "जिस चीज़ के लिए आए हैं, सीधे उसी पर।"},
}


def _hub_t(key: str, lang: str) -> str:
    e = HUB_T[key]
    return e.get(lang) or e["en"]


def hub_strings(lang: str) -> dict:
    s = {}
    for k in ("lang_label", "stat_mandis", "stat_states", "stat_crops", "stat_free",
              "cta_h", "cta_p", "cta_btn", "email_line", "footer_note"):
        s[k] = escape(t(k, lang))
    for k in HUB_T:
        s[k] = escape(_hub_t(k, lang))
    for u in dict.fromkeys(NAV_URLS + CORE):
        s["l:" + u] = escape(label(u, lang))
        s["s:" + u] = escape(_sub(u, lang))
    return s


# Shared social-card tags. og:locale is language_TERRITORY ("ar_AE"), not a
# bare language code — Facebook/WhatsApp ignore a bare "ar". The country code
# doubles as the territory except for the UK, whose ISO code is GB.
OG_IMAGE = f"{SITE}/images/og-banner.webp"


def og_locale(lang: str, code: str) -> str:
    return f"{lang}_{'GB' if code == 'uk' else code.upper()}"


def social_tags(title: str, desc: str) -> str:
    t, d = escape(title), escape(desc)
    return f"""<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1024">
<meta property="og:image:height" content="556">
<meta property="og:image:alt" content="{t}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{OG_IMAGE}">
<meta name="theme-color" content="#1a4d2e">"""


def render_hub() -> str:
    lang = HUB_LANGS[0]
    title = "KrashiMitra International — India's mandi prices from anywhere"
    desc = (f"Check India's mandi bhav, district maps and kisan yojana from {len(COUNTRIES)} "
            "countries, each page in that country's own language. 650+ mandis, daily, free.")
    url = f"{SITE}/international"
    cards = "".join(
        f'<a class="icard" href="/{c.code}"><b>{escape(c.flag)} {escape(c.name_en)}</b>'
        f'<span>{escape(LANGS[c.lang]["name"])}</span></a>' for c in COUNTRIES)
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "CollectionPage",
        "@id": url + "#page", "url": url, "name": title, "description": desc,
        "inLanguage": lang,
        "hasPart": [{"@type": "WebPage", "name": c.name_en, "url": c.url,
                     "inLanguage": c.lang} for c in COUNTRIES]}, ensure_ascii=False)
    island = json.dumps({
        "def": lang, "langs": HUB_LANGS,
        "meta": {l: {"dir": LANGS[l]["dir"], "html": l} for l in HUB_LANGS},
        "s": {l: hub_strings(l) for l in HUB_LANGS if l != lang},
    }, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="/analytics.js"></script>
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta property="og:type" content="website">
<meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="en_IN">
{social_tags(title, desc)}
<link rel="icon" href="/assets/favicon.ico">
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/km-shell.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&family=Noto+Serif+Devanagari:wght@700;800&display=swap" rel="stylesheet">
<script type="application/ld+json">{ld}</script>
<style>{CSS}{LANG_CSS}</style>
</head>
<body>
{header(lang)}
<div id="km-i18n-root" dir="ltr">
<header class="ihero">
  <div class="iw">
    {_lang_picker(HUB_LANGS, lang)}
    <span class="ibadge">🌍 International</span>
    <h1 data-i18n="hub_h1">{escape(_hub_t("hub_h1", lang))}</h1>
    <p data-i18n="hub_sub">{escape(_hub_t("hub_sub", lang))}</p>
    <div class="istats">
      <div class="istat"><b>650+</b><span data-i18n="stat_mandis">{escape(t("stat_mandis", lang))}</span></div>
      <div class="istat"><b>20+</b><span data-i18n="stat_states">{escape(t("stat_states", lang))}</span></div>
      <div class="istat"><b>150+</b><span data-i18n="stat_crops">{escape(t("stat_crops", lang))}</span></div>
      <div class="istat"><b>₹0</b><span data-i18n="stat_free">{escape(t("stat_free", lang))}</span></div>
    </div>
  </div>
</header>

<main class="iw">
  <section class="isec">
    <h2 class="ih2" data-i18n="hub_pick_h">{escape(_hub_t("hub_pick_h", lang))}</h2>
    <p class="isub" data-i18n="hub_pick_sub">{escape(_hub_t("hub_pick_sub", lang))}</p>
    <div class="igrid three">{cards}</div>
  </section>

  <section class="isec">
    <h2 class="ih2" data-i18n="hub_direct_h">{escape(_hub_t("hub_direct_h", lang))}</h2>
    <p class="isub" data-i18n="hub_direct_sub">{escape(_hub_t("hub_direct_sub", lang))}</p>
    {_cards(CORE, lang, three=True)}
  </section>

  <div class="iend">
    <h2 data-i18n="cta_h">{escape(t("cta_h", lang))}</h2>
    <p data-i18n="cta_p">{escape(t("cta_p", lang))}</p>
    <a class="ibtn" href="/bhav" data-i18n="cta_btn">{escape(t("cta_btn", lang))}</a>
  </div>
</main>
</div><!-- /#km-i18n-root -->
{footer(lang)}
<script type="application/json" id="km-i18n">{island}</script>
<script>{LANG_JS}</script>
<script src="/header-scroll.js"></script>
<script src="/drawer-menu.js"></script>
<script src="/bottomnav.js" defer></script>
</body>
</html>
"""


def redirects_block() -> str:
    """The _redirects lines these files need, so adding a country never
    silently ships a page Netlify will not serve.

    Languages need no rule of their own: every language of a country page
    lives at that country's one URL — see the header."""
    lines = ["# ── International country pages ─────────────────────────────",
             "# Generated by tools/build_international.py — keep in sync with COUNTRIES.",
             "# File: frontend/international/{code}.html → URL: /{code} and /international/{code}"]
    for c in COUNTRIES:
        lines.append(f"/{c.code}{' ' * (4 - len(c.code))}  /international/{c.code}.html   200")
    for c in COUNTRIES:
        lines.append(f"/international/{c.code}   /international/{c.code}.html   200")
    lines += ["/international      /international/index.html 200",
              "/international/*    /international/index.html 200",
              "/global             /international/index.html 200"]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any page on disk differs from the template")
    ap.add_argument("--redirects", action="store_true",
                    help="print the _redirects block and exit")
    ap.add_argument("--langs", action="store_true",
                    help="print each country's language toggle and exit")
    args = ap.parse_args()

    if args.redirects:
        print(redirects_block())
        return 0

    if args.langs:
        for c in COUNTRIES:
            names = " · ".join(LANGS[l]["name"] for l in c.langs)
            print(f"/{c.code:<3} {c.name_en:<22} {names}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = {"index.html": render_hub()}
    for c in COUNTRIES:
        pages[f"{c.code}.html"] = render(c)

    if args.check:
        stale = []
        for name, html in pages.items():
            p = OUT_DIR / name
            if not p.is_file() or p.read_text(encoding="utf-8") != html:
                stale.append(name)
        if stale:
            print("stale — run python tools/build_international.py:\n  " +
                  "\n  ".join(stale))
            return 1
        print(f"{len(pages)} international pages are current")
        return 0

    for name, html in pages.items():
        (OUT_DIR / name).write_text(html, encoding="utf-8")
    print(f"wrote {len(pages)} pages to {OUT_DIR.relative_to(ROOT)}")

    # Any file left over from the hand-written era that no longer has a row
    # in COUNTRIES would keep being served and keep making its old claims.
    known = set(pages)
    orphans = [f.name for f in OUT_DIR.glob("*.html") if f.name not in known]
    if orphans:
        print("  ORPHANS (no COUNTRIES row — delete or add the row): " + ", ".join(orphans))
    return 0


if __name__ == "__main__":
    sys.exit(main())
