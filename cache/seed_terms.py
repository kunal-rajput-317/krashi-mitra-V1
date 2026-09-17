# -*- coding: utf-8 -*-
# ============================================================
# cache/seed_terms.py
# The vocabulary the seeded Q&A corpus is matched with.
#
# WHY THIS EXISTS
# ---------------
# On production CACHE_SEMANTIC_ENABLED=false (render.yaml) — the torch stack
# does not fit in 512 MB. So the only matcher the chat actually has in front of
# a farmer is text, and the one it had was SequenceMatcher at ratio 0.94:
# effectively an exact-string match. A corpus of a thousand curated answers is
# worth nothing behind a matcher that needs the question typed the same way it
# was written.
#
# This module is the cheap half of the fix: fold a word to a canonical form, and
# map the spellings a farmer actually types onto one token. "गेहूं", "गेहूँ",
# "gehu", "gehun", "gehoon" and "wheat" are one word to a farmer and have to be
# one token here. It is a table, not a transliterator — transliteration puts the
# inherent vowel back ("सरसों" -> "sarason") and then no fold reaches "sarso",
# which is what people actually type. A table is smaller, exact, reviewable.
#
# It is also where the wrong-crop gate gets its crop names. That gate is the
# rule /sawal was built around: a wheat answer handed to a soybean question is
# worse than no answer, because it names a chemical.
#
# Zero dependencies on purpose — numpy, torch and the embedding model are all
# things this path has to keep working without.
# ============================================================

from __future__ import annotations

import re

# ── word folding ──────────────────────────────────────────────
# Latin: kill the spelling variance Hinglish has and Devanagari does not —
# doubled vowels for length (gehoon/gehun), ph/f, z/j, v/w, and the trailing
# vowel that changes with gender and number (kitna/kitni/kitne).
_LATIN_SUBS = (
    ("ee", "i"), ("oo", "u"), ("aa", "a"), ("ou", "u"),
    ("ph", "f"), ("z", "j"), ("w", "v"), ("x", "ks"), ("q", "k"),
)
_REPEAT = re.compile(r"(.)\1+")

# Devanagari: the marks that are written or dropped at will — anusvara,
# chandrabindu, nukta — and the long/short vowel pairs that are the same sound
# to the ear ("गेहूं" / "गेहुं").
_DEVA_DROP = str.maketrans("", "", "ँंः़्")
_DEVA_SHORTEN = str.maketrans({
    "ी": "ि",   # ी -> ि
    "ू": "ु",   # ू -> ु
    "ई": "इ",   # ई -> इ
    "ऊ": "उ",   # ऊ -> उ
    "ौ": "ो",   # ौ -> ो
    "ै": "े",   # ै -> े
    "आ": "अ",   # आ -> अ
    "ऑ": "ओ",   # ऑ -> ओ
})
_DEVA_MATRA = "ािीुूृेैोौ"
_DEVA_RE = re.compile(r"[ऀ-ॿ]")


def _is_deva(word: str) -> bool:
    return bool(_DEVA_RE.search(word))


def fold(word: str) -> str:
    """One word -> the canonical shape this index stores it under."""
    w = (word or "").strip().lower()
    if not w:
        return ""
    if _is_deva(w):
        w = w.translate(_DEVA_DROP).translate(_DEVA_SHORTEN)
        # A trailing vowel sign carries case and gender, not meaning:
        # "कितना" / "कितनी" / "कितने" are one question.
        while len(w) > 3 and w[-1] in _DEVA_MATRA:
            w = w[:-1]
        return w
    w = re.sub(r"[^a-z0-9]", "", w)
    if not w:
        return ""
    for a, b in _LATIN_SUBS:
        w = w.replace(a, b)
    w = _REPEAT.sub(r"\1", w)
    while len(w) > 4 and w[-1] in "naeiyh":
        w = w[:-1]
    return w


# ── the alias table ───────────────────────────────────────────
# canonical token -> every spelling that means it. Devanagari first, then the
# Hinglish a phone keyboard produces, then English where a farmer types it.
# Folding is applied to both sides, so only genuinely different spellings need
# listing — "गेहूँ" and "gehoon" both arrive as variants of "गेहूं" / "gehu".
TERMS: dict[str, tuple[str, ...]] = {
    # ── cereals ──
    "wheat":     ("गेहूं", "गेहूँ", "गेहु", "गेंहू", "gehu", "gehun", "gehoon", "genhu", "wheat", "kanak"),
    "paddy":     ("धान", "चावल", "झोना", "dhan", "dhaan", "paddy", "rice", "chawal", "jhona"),
    "maize":     ("मक्का", "मकई", "भुट्टा", "makka", "makke", "makai", "maize", "corn", "bhutta"),
    "bajra":     ("बाजरा", "बाजरी", "bajra", "bajre", "bajri", "millet"),
    "jowar":     ("ज्वार", "चरी", "jowar", "jwar", "sorghum", "chari"),
    "barley":    ("जौ", "jau", "jav", "barley"),
    "ragi":      ("रागी", "मंडुआ", "ragi", "mandua"),
    # ── cash crops ──
    "sugarcane": ("गन्ना", "ईख", "ऊख", "ganna", "ganne", "ganno", "ikh", "ukh", "sugarcane", "cane"),
    "cotton":    ("कपास", "नरमा", "रुई", "kapas", "narma", "cotton"),
    "mustard":   ("सरसों", "राई", "तोरिया", "sarson", "sarso", "rai", "toria", "mustard", "rapeseed"),
    "soybean":   ("सोयाबीन", "सोयबीन", "soyabean", "soybean", "soya"),
    "groundnut": ("मूंगफली", "मुंगफली", "moongfali", "mungfali", "groundnut", "peanut"),
    "sesame":    ("तिल", "til", "sesame", "gingelly"),
    "sunflower": ("सूरजमुखी", "surajmukhi", "sunflower"),
    "linseed":   ("अलसी", "alsi", "linseed", "flax"),
    "castor":    ("अरंडी", "arandi", "castor"),
    "jute":      ("जूट", "पटसन", "jute", "patsan"),
    "tobacco":   ("तंबाकू", "tambaku", "tobacco"),
    # ── pulses ──
    "gram":      ("चना", "चने", "बूट", "chana", "chane", "gram", "chickpea"),
    "lentil":    ("मसूर", "masoor", "masur", "lentil"),
    "pigeonpea": ("अरहर", "तूर", "तुअर", "arhar", "tur", "toor", "pigeonpea"),
    "greengram": ("मूंग", "moong", "mung", "munga"),
    "blackgram": ("उड़द", "उरद", "urad", "urd"),
    "pea":       ("मटर", "matar", "pea", "peas"),
    "cowpea":    ("लोबिया", "चौला", "lobia", "cowpea"),
    "rajma":     ("राजमा", "rajma"),
    # ── vegetables ──
    "potato":    ("आलू", "alu", "aloo", "potato"),
    "onion":     ("प्याज", "प्याज़", "pyaj", "pyaz", "onion", "kanda"),
    "tomato":    ("टमाटर", "tamatar", "tomato"),
    "garlic":    ("लहसुन", "lahsun", "lehsun", "garlic"),
    "chilli":    ("मिर्च", "मिर्ची", "mirch", "mirchi", "chilli", "chili", "capsicum", "शिमला"),
    "brinjal":   ("बैंगन", "भंटा", "baingan", "brinjal", "eggplant"),
    "okra":      ("भिंडी", "bhindi", "okra", "ladyfinger"),
    "cole":      ("गोभी", "फूलगोभी", "पत्तागोभी", "बंदगोभी", "gobhi", "gobi", "cauliflower", "cabbage"),
    "cucurbit":  ("लौकी", "कद्दू", "तोरई", "करेला", "खीरा", "ककड़ी", "तरबूज", "खरबूजा", "पेठा",
                  "lauki", "kaddu", "torai", "karela", "khira", "kakdi", "tarbuj", "kharbuja",
                  "gourd", "pumpkin", "cucumber", "watermelon", "muskmelon"),
    "carrot":    ("गाजर", "gajar", "carrot"),
    "radish":    ("मूली", "muli", "mooli", "radish"),
    "leafy":     ("पालक", "मेथी", "धनिया", "साग", "palak", "methi", "dhaniya", "spinach",
                  "fenugreek", "coriander"),
    "ginger":    ("अदरक", "adrak", "ginger"),
    "turmeric":  ("हल्दी", "haldi", "turmeric"),
    "mushroom":  ("मशरूम", "खुंभी", "mushroom", "khumbi"),
    # ── fruits ──
    "mango":     ("आम", "अंबिया", "aam", "aamo", "mango", "ambiya"),
    "banana":    ("केला", "kela", "kele", "banana"),
    "guava":     ("अमरूद", "amrud", "amrood", "guava"),
    "papaya":    ("पपीता", "papita", "papaya"),
    "citrus":    ("नींबू", "संतरा", "किन्नू", "मौसमी", "nimbu", "santra", "kinnu", "mausami",
                  "citrus", "orange", "lemon", "malta"),
    "litchi":    ("लीची", "lichi", "litchi", "lychee"),
    "grapes":    ("अंगूर", "angur", "angoor", "grapes"),
    "pomegranate": ("अनार", "anar", "pomegranate"),
    "apple":     ("सेब", "seb", "apple"),
    "aonla":     ("आंवला", "amla", "aonla", "awla"),
    "ber":       ("बेर", "ber", "jujube"),
    "sapota":    ("चीकू", "chiku", "sapota"),
    "coconut":   ("नारियल", "nariyal", "coconut"),
    "arecanut":  ("सुपारी", "supari", "arecanut"),
    "fodder":    ("बरसीम", "चारा", "नेपियर", "रिजका", "berseem", "chara", "napier", "rijka",
                  "fodder", "lucerne", "silage", "साइलेज"),
    # ── livestock ──
    "cow":       ("गाय", "गौ", "बछड़ा", "gay", "gai", "cow", "cattle", "calf"),
    "buffalo":   ("भैंस", "भैस", "bhains", "buffalo", "murrah"),
    "goat":      ("बकरी", "बकरा", "bakri", "goat", "sheep", "भेड़", "bhed"),
    "poultry":   ("मुर्गी", "मुर्गा", "चूजा", "अंडा", "murgi", "poultry", "chicken", "anda",
                  "egg", "chuja"),
    "fish":      ("मछली", "machhli", "fish", "fishery", "मत्स्य", "matsya"),
    "bee":       ("मधुमक्खी", "शहद", "madhumakkhi", "honey", "bee", "apiary"),
    # ── inputs ──
    "urea":      ("यूरिया", "urea", "yuria", "yuriya", "नाइट्रोजन", "nitrogen"),
    "dap":       ("डीएपी", "dap", "diammonium"),
    "ssp":       ("एसएसपी", "ssp", "फॉस्फोरस", "phosphorus"),
    "mop":       ("एमओपी", "पोटाश", "म्यूरेट", "mop", "potash", "potassium"),
    "npk":       ("एनपीके", "npk", "complex"),
    "zinc":      ("जिंक", "जस्ता", "zinc", "jinc"),
    "sulphur":   ("सल्फर", "गंधक", "sulphur", "sulfur", "gandhak"),
    "gypsum":    ("जिप्सम", "gypsum", "jipsam"),
    "manure":    ("गोबर", "कंपोस्ट", "वर्मीकंपोस्ट", "खाद", "जैविक", "gobar", "compost",
                  "vermicompost", "khad", "jaivik", "manure", "fym", "organic"),
    "biofert":   ("राइजोबियम", "पीएसबी", "एजोटोबैक्टर", "rhizobium", "psb", "azotobacter",
                  "biofertilizer"),
    "seed":      ("बीज", "beej", "bij", "seed", "किस्म", "kism", "prajati", "प्रजाति", "variety"),
    "pesticide": ("कीटनाशक", "दवा", "दवाई", "स्प्रे", "छिड़काव", "kitnashak", "dawa", "davai",
                  "spray", "chhidkav", "pesticide", "insecticide"),
    "fungicide": ("फफूंदनाशक", "फंगीसाइड", "fungicide", "फफूंद", "fafund"),
    "herbicide": ("खरपतवारनाशी", "नींदानाशक", "herbicide", "weedicide", "खरपतवार", "kharpatwar",
                  "नींदा", "ninda", "weed", "घास", "ghas"),
    "neem":      ("नीम", "neem", "नीमास्त्र"),
    # ── operations ──
    "sowing":    ("बुवाई", "बिजाई", "रोपाई", "बोना", "रोपण", "buvai", "bijai", "buai", "ropai",
                  "bona", "sowing", "planting", "transplanting", "nursery", "नर्सरी"),
    "harvest":   ("कटाई", "हार्वेस्ट", "katai", "harvest", "मड़ाई", "madai"),
    "irrigation": ("सिंचाई", "पानी", "पलेवा", "sinchai", "pani", "paani", "irrigation", "water",
                   "ड्रिप", "drip", "स्प्रिंकलर", "sprinkler", "tubewell", "नलकूप"),
    "ploughing": ("जुताई", "जोत", "jutai", "ploughing", "tillage", "रोटावेटर", "rotavator"),
    "storage":   ("भंडारण", "गोदाम", "स्टोर", "bhandaran", "godam", "storage", "warehouse"),
    "yield":     ("उपज", "पैदावार", "उत्पादन", "upaj", "paidawar", "yield", "production",
                  "क्विंटल", "quintal"),
    "spacing":   ("दूरी", "फासला", "कतार", "duri", "faasla", "katar", "spacing", "row"),
    "treatment": ("उपचार", "बीजोपचार", "upchar", "bijopchar", "इलाज", "ilaj"),
    # ── problems ──
    "disease":   ("रोग", "बीमारी", "बिमारी", "rog", "bimari", "disease", "infection"),
    "pest":      ("कीट", "कीड़ा", "कीड़े", "सुंडी", "इल्ली", "kit", "kida", "kide", "sundi",
                  "illi", "pest", "insect", "caterpillar", "borer", "छेदक", "chhedak"),
    "rust":      ("रतुआ", "गेरुआ", "ratua", "gerua", "rust"),
    "blight":    ("झुलसा", "अंगमारी", "jhulsa", "angmari", "blight"),
    "wilt":      ("उकठा", "मुरझान", "विल्ट", "ukatha", "wilt", "murjhan"),
    "rot":       ("सड़न", "गलन", "sadan", "galan", "rot"),
    "smut":      ("कंडुआ", "कंडवा", "kandua", "smut"),
    "aphid":     ("माहू", "चेपा", "एफिड", "mahu", "chepa", "aphid"),
    "whitefly":  ("सफेद मक्खी", "whitefly", "safed makkhi"),
    "termite":   ("दीमक", "dimak", "termite"),
    "rodent":    ("चूहा", "चूहे", "chuha", "chuhe", "rat", "rodent"),
    "nematode":  ("सूत्रकृमि", "निमेटोड", "nematode"),
    "deficiency": ("कमी", "पीलापन", "पीली", "पीला", "kami", "pila", "pili", "yellow",
                   "deficiency", "yellowing"),
    "lodging":   ("गिरना", "लॉजिंग", "girna", "lodging"),
    "frost":     ("पाला", "शीतलहर", "pala", "frost"),
    "hail":      ("ओला", "ओलावृष्टि", "ola", "hail", "hailstorm"),
    "drought":   ("सूखा", "sukha", "drought"),
    "waterlog":  ("जलभराव", "जलजमाव", "jalbharav", "waterlogging", "flood", "बाढ़", "badh"),
    "salinity":  ("ऊसर", "बंजर", "क्षारीय", "लवणीय", "usar", "banjar", "saline", "alkaline",
                  "reh", "रेह"),
    # ── money / market / schemes ──
    "price":     ("भाव", "दाम", "कीमत", "रेट", "मूल्य", "bhav", "bhaav", "daam", "rate",
                  "price", "kimat"),
    "mandi":     ("मंडी", "बाजार", "एपीएमसी", "mandi", "market", "apmc", "बाज़ार"),
    "msp":       ("एमएसपी", "msp", "खरीद", "kharid", "procurement"),
    "loan":      ("ऋण", "कर्ज", "लोन", "केसीसी", "rin", "karj", "loan", "kcc"),
    "subsidy":   ("अनुदान", "सब्सिडी", "छूट", "anudan", "subsidy", "chhut"),
    "insurance": ("बीमा", "bima", "insurance", "pmfby", "पीएमएफबीवाई"),
    "scheme":    ("योजना", "सरकारी", "yojana", "yojna", "scheme", "sarkari", "government"),
    "pmkisan":   ("pmkisan", "nidhi", "निधि"),
    "enam":      ("ईनाम", "enam"),
    "fpo":       ("एफपीओ", "fpo"),
    "parchi":    ("पर्ची", "सट्टा", "parchi", "satta"),
    "registry":  ("पंजीकरण", "रजिस्ट्रेशन", "panjikaran", "registration", "आवेदन", "avedan",
                  "apply"),
    # ── site features ──
    "weather":   ("मौसम", "बारिश", "बरसात", "तापमान", "mausam", "barish", "barsat", "weather",
                  "rain"),
    "app":       ("ऐप", "वेबसाइट", "साइट", "app", "website", "krashimitra"),
    "rental":    ("किराया", "किराए", "भाड़ा", "kiraya", "kiraye", "bhada", "rent", "rental",
                  "ट्रैक्टर", "tractor", "मशीन", "machine"),
    "shop":      ("दुकान", "dukan", "shop"),
    # ── what the farmer is actually asking for ──
    # These are the difference between two questions that share every other
    # word: "गेहूं में यूरिया कब" and "गेहूं में यूरिया कितना" are not the same
    # question. They are canonicalised across scripts for exactly that reason —
    # dropping them as stopwords would merge answers that must not merge.
    "when":      ("कब", "समय", "कालः", "kab", "samay", "time", "season", "मौसमी समय"),
    "howmuch":   ("कितना", "कितनी", "कितने", "मात्रा", "डोज", "kitna", "kitni", "kitne",
                  "matra", "dose", "quantity", "howmuch"),
    "how":       ("कैसे", "कैसा", "विधि", "तरीका", "तरीके", "kaise", "kaisa", "vidhi",
                  "tarika", "how", "method"),
    "which":     ("कौन", "कौनसा", "कौनसी", "किस", "kaun", "kaunsa", "konsa", "kis", "which"),
    "why":       ("क्यों", "क्युं", "kyun", "kyon", "why"),
    "soil":      ("मिट्टी", "मृदा", "भूमि", "जमीन", "ज़मीन", "mitti", "mrida", "bhumi",
                  "jamin", "zameen", "soil", "land", "पीएच", "ph"),
    "where":     ("कहां", "कहाँ", "kahan", "where"),
    "apply":     ("डालें", "डालना", "डाले", "देना", "देंगे", "dalen", "dalna", "dale", "dena",
                  "apply", "डालूं"),
    "mosaic":    ("मोजेक", "मोज़ेक", "mosaic", "चितेरी"),
    "grading":   ("ग्रेडिंग", "छंटाई", "grading", "sorting", "chhatai"),
    "profit":    ("मुनाफा", "फायदा", "आमदनी", "कमाई", "munafa", "fayda", "aamdani", "kamai",
                  "profit", "income"),
    "cost":      ("लागत", "खर्च", "lagat", "kharch", "cost", "expense"),
}

# Two words that mean one thing, written out the way a farmer types them. They
# are folded at import, so nothing here has to be spelled in fold()'s output
# form. "pm kisan" is a scheme; "kisan" on its own is just the word "farmer",
# which is why this cannot be done with single-word aliases.
_PHRASE_SOURCE: dict[str, tuple[str, ...]] = {
    "pmkisan":     ("पीएम किसान", "pm kisan", "किसान सम्मान", "kisan samman",
                    "सम्मान निधि", "samman nidhi"),
    "whitefly":    ("सफेद मक्खी", "safed makkhi", "white fly"),
    "chilli":      ("शिमला मिर्च", "simla mirch", "shimla mirch"),
    "ssp":         ("सिंगल सुपर", "single super"),
    "soilcard":    ("मृदा स्वास्थ्य", "soil health", "मिट्टी जांच", "मिट्टी की जांच",
                    "soil test", "soil testing", "मृदा परीक्षण"),
    "seeddrill":   ("सीड ड्रिल", "seed drill", "बीज ड्रिल"),
    "happyseeder": ("हैप्पी सीडर", "happy seeder"),
    "seedrate":    ("बीज दर", "seed rate", "बीज की मात्रा"),
    "drip":        ("ड्रिप सिंचाई", "drip irrigation", "टपक सिंचाई"),
    "kcc":         ("किसान क्रेडिट", "kisan credit", "क्रेडिट कार्ड", "credit card"),
    "pmfby":       ("फसल बीमा", "fasal bima", "crop insurance", "प्रधानमंत्री फसल"),
    "greenmanure": ("हरी खाद", "hari khad", "green manure", "ढैंचा", "dhaincha"),
    "nanourea":    ("नैनो यूरिया", "nano urea"),
    "fallarmyworm": ("फॉल आर्मीवर्म", "fall armyworm", "सैनिक कीट", "fauji kida"),
    "msp":         ("समर्थन मूल्य", "support price", "न्यूनतम समर्थन"),
    "enam":        ("ई नाम", "e nam"),
    "fpo":         ("किसान उत्पादक", "farmer producer"),
    "pmkusum":     ("पीएम कुसुम", "pm kusum", "सोलर पंप", "solar pump"),
}

# Reverse map: every folded single-word variant -> its canonical token. A
# multi-word variant is NOT split across this map — "सफेद मक्खी" is whitefly,
# but "सफेद" on its own is the colour white. Those go through PHRASES instead.
_ALIAS: dict[str, str] = {}
for _canon, _variants in TERMS.items():
    for _v in (_canon,) + _variants:
        if len(str(_v).split()) != 1:
            continue
        _f = fold(_v)
        if _f and _f not in _ALIAS:
            _ALIAS[_f] = _canon

# ── crops, for the wrong-crop gate ────────────────────────────
# A canonical token that names a crop or an animal. A question that names one of
# these and a stored answer filed under a different one must never be paired:
# that is the /sawal rule, and it matters more here because these answers carry
# doses.
CROP_TOKENS: frozenset[str] = frozenset({
    "wheat", "paddy", "maize", "bajra", "jowar", "barley", "ragi",
    "sugarcane", "cotton", "mustard", "soybean", "groundnut", "sesame",
    "sunflower", "linseed", "castor", "jute", "tobacco",
    "gram", "lentil", "pigeonpea", "greengram", "blackgram", "pea", "cowpea", "rajma",
    "potato", "onion", "tomato", "garlic", "chilli", "brinjal", "okra", "cole",
    "cucurbit", "carrot", "radish", "leafy", "ginger", "turmeric", "mushroom",
    "mango", "banana", "guava", "papaya", "citrus", "litchi", "grapes",
    "pomegranate", "apple", "aonla", "ber", "sapota", "coconut", "arecanut", "fodder",
    "cow", "buffalo", "goat", "poultry", "fish", "bee",
})

# ── stopwords ─────────────────────────────────────────────────
# Deliberately short. Question words (कब / कितना / कैसे / कौन) are NOT here:
# "गेहूं में यूरिया कब डालें" and "गेहूं में यूरिया कितना डालें" are different
# questions with different answers, and dropping the interrogative merges them.
STOPWORDS: frozenset[str] = frozenset(
    fold(w) for w in (
        "का", "की", "के", "को", "में", "मे", "से", "पर", "है", "हैं", "हूं", "हूँ",
        "और", "या", "भी", "ही", "तो", "यह", "वह", "इस", "उस", "एक", "जो", "कि",
        "लिए", "लिये", "रहा", "रही", "रहे", "गया", "गई", "हो", "हुआ", "हुई",
        "मेरा", "मेरी", "मेरे", "हमारा", "हमारे", "आप", "मैं", "मुझे", "अपने", "अपनी",
        "जी", "बताओ", "बताइए", "बताएं", "please", "plz", "नहीं", "न",
        "ka", "ki", "ke", "ko", "me", "mein", "mai", "se", "par", "hai", "hain", "hun",
        "aur", "ya", "bhi", "hi", "to", "yah", "ye", "wo", "is", "us", "ek", "jo",
        "liye", "raha", "rahi", "rahe", "gaya", "gayi", "ho", "hua", "hui",
        "mera", "meri", "mere", "hamara", "hamare", "aap", "main", "mujhe", "apne",
        "the", "a", "an", "of", "in", "on", "for", "are", "my", "i", "and",
        "batao", "bataye", "bataiye", "sir", "nahi",
    )
)

# Built here, below STOPWORDS, because a phrase is matched against the token
# stream AFTER stopwords are dropped: "मिट्टी की जांच" arrives as two tokens.
# Multi-word variants sitting in TERMS are folded into phrases too, so a term
# only ever has to be written once.
PHRASES: dict[tuple[str, str], str] = {}
for _canon, _phrases in list(_PHRASE_SOURCE.items()) + [
    (_c, tuple(v for v in _vs if len(str(v).split()) > 1)) for _c, _vs in TERMS.items()
]:
    for _p in _phrases:
        _parts = [fold(x) for x in str(_p).split()]
        _parts = [x for x in _parts if x and x not in STOPWORDS]
        if len(_parts) >= 2:
            PHRASES.setdefault((_parts[0], _parts[1]), _canon)

_SPLIT = re.compile(r"[^\wऀ-ॿ]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    """Text -> canonical tokens, stopwords dropped, order preserved."""
    folded: list[str] = []
    for raw in _SPLIT.split(text or ""):
        f = fold(raw)
        if not f or f in STOPWORDS:
            continue
        folded.append(f)

    out: list[str] = []
    i = 0
    while i < len(folded):
        pair = (folded[i], folded[i + 1]) if i + 1 < len(folded) else None
        if pair in PHRASES:
            out.append(PHRASES[pair])
            i += 2
            continue
        out.append(_ALIAS.get(folded[i], folded[i]))
        i += 1
    return out


def crops_in(text: str) -> set[str]:
    """Every crop this text names — the input to the wrong-crop gate."""
    return {t for t in tokens(text) if t in CROP_TOKENS}
