# -*- coding: utf-8 -*-
# ============================================================
# KrashiMitra — the spray/dose advisory that every article carrying
# agro-chemistry must show.
#
# WHY THIS EXISTS
# ---------------
# The articles were generated, not written by an agronomist, and 62 of the 139
# name a pesticide or print a dose. They now rank in front of a very large
# number of searches. A farmer who sprays the wrong quantity on the strength of
# a page on this site loses a crop, and the page — not the label — is what he
# will say he followed.
#
# Under the Insecticides Act, 1968 the APPROVED LABEL on the container is the
# legal instruction: crop, dose and waiting period all come from there, and
# using a product off-label is the offence. So the defensible position is not
# "our numbers are right" — it is "the label is the authority, this is general
# information, confirm with your KVK". That is what this block says, in the
# reader's own language, on the page itself rather than buried in Terms. Same
# stance as the connector disclaimer on /krashi_dukan.
#
# HOW IT IS WIRED
# ---------------
# article_builder.render() calls needs_advisory() on the article's own body and
# injects advisory_html() when it trips. There is no per-article opt-in,
# because an author who has to remember a disclaimer is an author who will
# forget it on the one page that needed it. validate() then FAILS THE BUILD for
# any page that trips the detector without carrying the block, so the two
# cannot drift apart.
#
# ARTICLE["advisory"] = True forces the block on for a page the detector cannot
# see (a veterinary dose, a product named only by brand). There is deliberately
# NO way to force it OFF: an article that names a chemical shows the advisory,
# and anyone "tidying up" by adding an off switch has removed the only thing
# here that does any work.
# ============================================================

from __future__ import annotations

import re

# The marker validate() looks for. Changing it silently disarms the gate, so it
# lives here, next to the markup that carries it.
ADVISORY_MARK = "data-km-advisory"

# ── what counts as agro-chemistry ──────────────────────────────────────────
# Active ingredients as they are actually spelled in these articles: Devanagari
# first (most pages), then Latin (Kannada/Tamil pages and brand copy tend to
# keep the Latin name). Spelling varies between authors — कार्बेन्डाजिम and
# कार्बेन्डाज़िम are both in use — so variants are listed, not normalised.
CHEMICALS = (
    # insecticides
    "इमिडाक्लोप्रिड", "थायोमेथोक्सम", "थायामेथोक्सम", "क्लोरपायरीफॉस",
    "क्लोरपाइरीफॉस", "इमामेक्टिन", "स्पिनोसैड", "साइपरमेथ्रिन", "क्विनालफॉस",
    "एसीफेट", "फिप्रोनिल", "क्लोरएंट्रानिलिप्रोल", "फ्लूबेंडियामाइड",
    "बुप्रोफेजिन", "डाइनोटेफ्यूरान", "पाइमेट्रोजिन", "डाइमेथोएट",
    "मोनोक्रोटोफॉस", "ऑक्सीडेमेटॉन", "प्रोफेनोफॉस", "इंडोक्साकार्ब",
    "नोवालुरॉन", "मैलाथियान", "मेलाथियान", "डेल्टामेथ्रिन", "बाइफेंथ्रिन",
    "एबामेक्टिन", "फेनवलरेट", "कार्बोफ्यूरान", "कार्टाप", "लैम्ब्डा",
    "साइहेलोथ्रिन", "थायोडिकार्ब", "डाइक्लोरवास",
    # fungicides
    "कार्बेन्डाजिम", "कार्बेन्डाज़िम", "मैंकोजेब", "मैन्कोजेब",
    "प्रोपिकोनाजोल", "हेक्साकोनाजोल", "टेबुकोनाजोल", "कॉपर ऑक्सीक्लोराइड",
    "मेटालैक्सिल", "एजोक्सीस्ट्रोबिन", "डाइफेनोकोनाजोल", "ट्राईसाइक्लाजोल",
    "थायरम", "कैप्टान", "क्लोरोथैलोनिल", "सल्फर", "गंधक", "वैलिडामाइसिन",
    "स्ट्रेप्टोसाइक्लिन", "स्ट्रेप्टोमाइसिन",
    # herbicides
    "ग्लाइफोसेट", "पैराक्वाट", "पेंडीमेथालिन", "एट्राजीन", "मेट्रिब्युजिन",
    "सल्फोसल्फ्यूरॉन", "क्लोडिनाफॉप", "पिनोक्साडेन", "आइसोप्रोट्यूरॉन",
    "मेटसल्फ्यूरॉन", "इमेजेथापायर", "ऑक्सीफ्लोरफेन", "बिसपायरीबैक",
    # bio-agents
    "ट्राइकोडर्मा", "ब्यूवेरिया", "बवेरिया", "मेटाराइजियम", "स्यूडोमोनास",
    # latin
    "imidacloprid", "thiamethoxam", "chlorpyriphos", "chlorpyrifos",
    "emamectin", "spinosad", "carbendazim", "mancozeb", "propiconazole",
    "hexaconazole", "tebuconazole", "metalaxyl", "cypermethrin",
    "cyhalothrin", "quinalphos", "acephate", "fipronil",
    "chlorantraniliprole", "flubendiamide", "buprofezin", "dinotefuran",
    "pymetrozine", "glyphosate", "paraquat", "pendimethalin", "atrazine",
    "metribuzin", "sulfosulfuron", "clodinafop", "pinoxaden", "isoproturon",
    "azoxystrobin", "difenoconazole", "streptocycline", "validamycin",
    "tricyclazole", "thiram", "captan", "dimethoate", "monocrotophos",
    "profenofos", "indoxacarb", "novaluron", "malathion", "deltamethrin",
    "bifenthrin", "abamectin", "carbofuran", "cartap", "trichoderma",
    "beauveria", "metarhizium", "pseudomonas", "2,4-D",
)
_CHEM_RE = re.compile("|".join(re.escape(c) for c in CHEMICALS), re.I)

# A quantity next to a rate unit: "2 ग्राम प्रति लीटर", "400-500 मिली/एकड़",
# "20 ಕೆಜಿ ಪ್ರತಿ ಎಕರೆ", "2 கிராம் ஒரு லிட்டர்". This catches the pages that
# print a dose without ever naming the molecule — the fertiliser and
# seed-treatment guides are full of those.
_AMOUNT = (r"(?:ग्राम|ग्रा\.?|मिलीलीटर|मिली|मि\.?ली\.?|किलोग्राम|किलो|किग्रा|"
           r"केजी|लीटर|एमएल|मिलीग्राम|क्विंटल|बोरी|"
           r"ಗ್ರಾಂ|ಮಿಲಿ|ಕೆಜಿ|ಕಿಲೋ|ಲೀಟರ್|"
           r"கிராம்|மில்லி|கிலோ|லிட்டர்|"
           r"ml|gm|kg|g|l)")
_PER = r"(?:/|प्रति|ಪ್ರತಿ|ஒரு|per)"
_BASE = (r"(?:लीटर|पानी|एकड़|हेक्टेयर|बीघा|पंप|टंकी|किलो|बीज|बोरी|पेड़|पौधा|"
         r"ಲೀಟರ್|ಎಕರೆ|ಹೆಕ್ಟೇರ್|ನೀರು|ಬೀಜ|"
         r"லிட்டர்|ஏக்கர்|ஹெக்டேர்|தண்ணீர்|விதை|"
         r"litre|liter|acre|ha|hectare)")
DOSE_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:(?:-|–|से|to)\s*\d+(?:[.,]\d+)?\s*)?"
    + _AMOUNT + r"\s*" + _PER + r"\s*" + _BASE, re.I)


def find_chemicals(text: str) -> list[str]:
    """Every active ingredient named in `text`, de-duplicated, in page order."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _CHEM_RE.finditer(text or ""):
        k = m.group(0).lower()
        if k not in seen:
            seen.add(k)
            out.append(m.group(0))
    return out


def find_doses(text: str) -> list[str]:
    """Every quantity-per-unit expression in `text`."""
    return [re.sub(r"\s+", " ", m.group(0)) for m in DOSE_RE.finditer(text or "")]


def needs_advisory(text: str) -> bool:
    """True when this page tells a farmer to put a substance on his crop."""
    return bool(_CHEM_RE.search(text or "") or DOSE_RE.search(text or ""))


# ── the block itself ───────────────────────────────────────────────────────
# Four claims, in this order, because that is the order that protects the
# reader: this is not a prescription → ask your KVK → the label is the
# authority (dose AND waiting period) → registration changes, so check it.
# The waiting-period line is not boilerplate: residue at harvest is how a wrong
# spray reaches someone who never read the page.
_COPY = {
    "hi": {
        "h": "ज़रूरी सूचना — दवा, खाद और मात्रा के बारे में",
        "p": ("इस लेख की जानकारी सामान्य मार्गदर्शन के लिए है, किसी एक खेत के लिए "
              "सिफ़ारिश नहीं। दवा, खाद और उनकी मात्रा फ़सल, अवस्था, मिट्टी और "
              "उत्पाद के हिसाब से बदलती है।"),
        "li": [
            "छिड़काव से पहले अपने नज़दीकी <strong>कृषि विज्ञान केंद्र (KVK)</strong> "
            "या ज़िला कृषि अधिकारी से पुष्टि ज़रूर करें।",
            "डिब्बे पर छपा <strong>लेबल ही अंतिम प्रमाण है</strong> — मात्रा, फ़सल "
            "और प्रतीक्षा अवधि (waiting period) वहीं से लें, इस लेख से नहीं।",
            "दवा उसी फ़सल पर डालें जिसके लिए वह <strong>CIB&amp;RC में पंजीकृत</strong> "
            "है। पंजीकरण और प्रतिबंध समय-समय पर बदलते रहते हैं।",
            "प्रतीक्षा अवधि पूरी हुए बिना फ़सल न तोड़ें — बचा हुआ अंश खाने वाले तक "
            "पहुँचता है।",
        ],
        "foot": ("KrashiMitra इस जानकारी के उपयोग से हुए किसी नुक़सान की "
                 "ज़िम्मेदारी नहीं लेता।"),
    },
    "kn": {
        "h": "ಮುಖ್ಯ ಸೂಚನೆ — ಔಷಧಿ, ಗೊಬ್ಬರ ಮತ್ತು ಪ್ರಮಾಣದ ಬಗ್ಗೆ",
        "p": ("ಈ ಲೇಖನದ ಮಾಹಿತಿ ಸಾಮಾನ್ಯ ಮಾರ್ಗದರ್ಶನಕ್ಕಾಗಿ ಮಾತ್ರ, ಯಾವುದೇ ಒಂದು "
              "ಹೊಲಕ್ಕೆ ನೀಡಿದ ಶಿಫಾರಸು ಅಲ್ಲ. ಔಷಧಿ, ಗೊಬ್ಬರ ಮತ್ತು ಅವುಗಳ ಪ್ರಮಾಣ ಬೆಳೆ, "
              "ಹಂತ, ಮಣ್ಣು ಮತ್ತು ಉತ್ಪನ್ನದ ಪ್ರಕಾರ ಬದಲಾಗುತ್ತದೆ."),
        "li": [
            "ಸಿಂಪಡಿಸುವ ಮೊದಲು ನಿಮ್ಮ ಹತ್ತಿರದ <strong>ಕೃಷಿ ವಿಜ್ಞಾನ ಕೇಂದ್ರ (KVK)</strong> "
            "ಅಥವಾ ಜಿಲ್ಲಾ ಕೃಷಿ ಅಧಿಕಾರಿಯಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.",
            "ಡಬ್ಬಿಯ ಮೇಲಿನ <strong>ಲೇಬಲ್ ಅಂತಿಮ ಆಧಾರ</strong> — ಪ್ರಮಾಣ, ಬೆಳೆ ಮತ್ತು "
            "ಕಾಯುವ ಅವಧಿಯನ್ನು ಅಲ್ಲಿಂದಲೇ ತೆಗೆದುಕೊಳ್ಳಿ, ಈ ಲೇಖನದಿಂದ ಅಲ್ಲ.",
            "ಯಾವ ಬೆಳೆಗೆ <strong>CIB&amp;RC ನೋಂದಣಿ</strong> ಇದೆಯೋ ಆ ಬೆಳೆಗೆ ಮಾತ್ರ "
            "ಬಳಸಿ. ನೋಂದಣಿ ಮತ್ತು ನಿಷೇಧ ಕಾಲಕಾಲಕ್ಕೆ ಬದಲಾಗುತ್ತದೆ.",
            "ಕಾಯುವ ಅವಧಿ ಮುಗಿಯುವ ಮೊದಲು ಕೊಯ್ಲು ಮಾಡಬೇಡಿ — ಉಳಿದ ಅಂಶ ತಿನ್ನುವವರಿಗೆ "
            "ತಲುಪುತ್ತದೆ.",
        ],
        "foot": ("ಈ ಮಾಹಿತಿಯ ಬಳಕೆಯಿಂದ ಆಗುವ ಯಾವುದೇ ನಷ್ಟಕ್ಕೆ KrashiMitra "
                 "ಜವಾಬ್ದಾರನಲ್ಲ."),
    },
    "en": {
        "h": "Important — about pesticides, fertilisers and doses",
        "p": ("The information in this article is general guidance, not a "
              "recommendation for any one field. The right product and its "
              "dose change with the crop, its stage, the soil and the brand."),
        "li": [
            "Confirm with your nearest <strong>Krishi Vigyan Kendra (KVK)</strong> "
            "or district agriculture officer before you spray.",
            "The <strong>label printed on the container is the authority</strong> "
            "— take the dose, the approved crop and the waiting period from "
            "there, not from this article.",
            "Use a product only on a crop it is <strong>registered for with "
            "CIB&amp;RC</strong>. Registrations and restrictions change from "
            "time to time.",
            "Do not harvest before the waiting period ends — residue reaches "
            "whoever eats the crop.",
        ],
        "foot": ("KrashiMitra accepts no liability for any loss arising from "
                 "the use of this information."),
    },
    "ta": {
        "h": "முக்கியத் தகவல் — மருந்து, உரம் மற்றும் அளவு குறித்து",
        "p": ("இக்கட்டுரையின் தகவல் பொதுவான வழிகாட்டுதலுக்கு மட்டுமே, ஒரு "
              "குறிப்பிட்ட வயலுக்கான பரிந்துரை அல்ல. மருந்து, உரம் மற்றும் "
              "அவற்றின் அளவு பயிர், வளர்ச்சி நிலை, மண் மற்றும் தயாரிப்பைப் "
              "பொறுத்து மாறும்."),
        "li": [
            "தெளிப்பதற்கு முன் அருகிலுள்ள <strong>வேளாண் அறிவியல் மையம் (KVK)</strong> "
            "அல்லது மாவட்ட வேளாண் அலுவலரிடம் உறுதிப்படுத்திக் கொள்ளுங்கள்.",
            "டப்பாவில் அச்சிடப்பட்ட <strong>லேபிளே இறுதி ஆதாரம்</strong> — அளவு, "
            "பயிர், காத்திருப்புக் காலம் அனைத்தையும் அங்கிருந்தே எடுங்கள், "
            "இக்கட்டுரையிலிருந்து அல்ல.",
            "எந்தப் பயிருக்கு <strong>CIB&amp;RC பதிவு</strong> உள்ளதோ அந்தப் "
            "பயிருக்கு மட்டுமே பயன்படுத்துங்கள். பதிவும் தடையும் அவ்வப்போது மாறும்.",
            "காத்திருப்புக் காலம் முடியும் முன் அறுவடை செய்யாதீர்கள் — எஞ்சிய "
            "மருந்து உண்பவரைச் சென்றடையும்.",
        ],
        "foot": ("இத்தகவலைப் பயன்படுத்துவதால் ஏற்படும் எந்த இழப்புக்கும் "
                 "KrashiMitra பொறுப்பல்ல."),
    },
}

_CSS = (
    "<style>"
    ".km-advisory{border:1px solid #e0b400;background:#fffbeb;"
    "border-left:5px solid #e0b400;border-radius:10px;padding:18px 20px;"
    "margin:28px 0;font-size:.97rem;line-height:1.75;color:#3d3312}"
    ".km-advisory h3{margin:0 0 10px;font-size:1.05rem;color:#8a6100}"
    ".km-advisory p{margin:0 0 10px}"
    ".km-advisory ul{margin:0 0 10px;padding-left:20px}"
    ".km-advisory li{margin:0 0 7px}"
    ".km-advisory .km-adv-foot{margin:0;font-size:.88rem;color:#6b5a2e;"
    "font-style:italic}"
    "@media(max-width:480px){.km-advisory{padding:15px 16px;font-size:.93rem}}"
    "</style>"
)


def advisory_html(lang: str = "hi") -> str:
    """The visible block. Self-contained — it carries its own CSS, so a
    redesign of SHELL_SOURCE cannot silently strip its styling."""
    c = _COPY.get(lang, _COPY["hi"])
    items = "\n".join("      <li>" + x + "</li>" for x in c["li"])
    return (
        "\n  <!-- Spray/dose advisory — tools/article_advisory.py -->\n  "
        + _CSS + "\n"
        '  <div class="km-advisory" ' + ADVISORY_MARK + '="1" role="note">\n'
        "    <h3>&#9888;&#65039; " + c["h"] + "</h3>\n"
        "    <p>" + c["p"] + "</p>\n"
        "    <ul>\n" + items + "\n    </ul>\n"
        '    <p class="km-adv-foot">' + c["foot"] + "</p>\n"
        "  </div>\n"
    )


# ── legacy pages ───────────────────────────────────────────────────────────
# 36 article pages predate the builder and have no content module, so render()
# can never reach them — and they are the WORSE half: hand-written crop guides
# averaging more chemical names than the generated ones, including the only
# page on the site that names glyphosate and paraquat. They get the same block,
# inserted directly into the HTML, and the same test then holds every page to
# the rule regardless of which path produced it.
#
# Insertion is idempotent: a page that already carries the mark is returned
# untouched, so the sweep is safe to re-run and safe to wire into a build.

def page_lang(doc: str) -> str:
    m = re.search(r'<html[^>]*\blang="([^"]+)"', doc)
    return (m.group(1) if m else "hi").split("-")[0]


def _anchor(doc: str) -> int | None:
    """Where the block goes: just above the pre-FAQ ad slot, else above the
    section holding the FAQ, else above the closing CTA. Returns an index."""
    i = doc.find("<!-- ── AD SLOT : before FAQ ── -->")
    if i != -1:
        return i
    f = doc.find('<div class="faq-item"')
    if f != -1:
        s = doc.rfind("<section", 0, f)
        if s != -1:
            return s
    c = doc.find('<div class="cta-block"')
    return c if c != -1 else None


def ensure_in_html(doc: str, lang: str | None = None) -> tuple[str, bool]:
    """Insert the advisory into a built article page if it needs one and does
    not already carry it. Returns (document, changed)."""
    if ADVISORY_MARK in doc:
        return doc, False
    own = re.split(r'<div class="relevant-articles">', doc)[0]
    text = re.sub(r"<script\b.*?</script>", " ", own, flags=re.S | re.I)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    if not needs_advisory(text):
        return doc, False
    at = _anchor(doc)
    if at is None:
        raise ValueError("no anchor found for the advisory block")
    block = advisory_html(lang or page_lang(doc))
    return doc[:at] + block.lstrip("\n") + "\n  " + doc[at:], True


def sweep(articles_dir, write: bool = True) -> list[str]:
    """Apply the advisory to every built article page that needs one.

    Idempotent, so it is safe to run on the whole directory after a build:
    pages the builder already handled carry the mark and are skipped, and only
    the module-less legacy pages are actually touched.
    """
    import pathlib
    changed = []
    for p in sorted(pathlib.Path(articles_dir).glob("*.html")):
        if p.stem == "index":
            continue
        doc = p.read_text(encoding="utf-8", errors="replace")
        new, did = ensure_in_html(doc)
        if did:
            changed.append(p.stem)
            if write:
                p.write_text(new, encoding="utf-8")
    return changed


if __name__ == "__main__":
    import argparse
    import pathlib

    ap = argparse.ArgumentParser(
        description="Add the spray/dose advisory to built article pages.")
    ap.add_argument("--check", action="store_true",
                    help="report what is missing, write nothing")
    ap.add_argument("--dir", type=pathlib.Path,
                    default=pathlib.Path(__file__).resolve().parents[1]
                    / "frontend" / "articles")
    ns = ap.parse_args()
    hit = sweep(ns.dir, write=not ns.check)
    verb = "would patch" if ns.check else "patched"
    print(f"{verb} {len(hit)} page(s)")
    for s in hit:
        print(f"  {s}")
    raise SystemExit(1 if (ns.check and hit) else 0)
