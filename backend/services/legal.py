"""The safety and liability sentences every section that shows goods must print.

Asked for directly on 18 Sep 2026: the "ध्यान दें" notice said whose the PRICE
was and nothing about whose the RISK is. Half this catalogue is कीटनाशक, खाद
and पशु आहार — things that burn a crop, poison a well or kill an animal when
they are mixed wrong — and a farmer who reads a chemical's name on our page and
loses a field reads it as our recommendation unless we say otherwise.

Two halves, and they do different work:

  * SAFETY — read the label and the dose, wear gloves, ask a real advisor, and
    know that what is written here is general information rather than advice
    for your field. This is the half that can actually prevent the harm.
  * LIABILITY — the goods, their genuineness, their effect and their use belong
    to the company that made them, the shop that sold them and the person who
    used them. We connect, and we do not carry that risk.

It lives in services/ rather than in routes/product.py for the reason the
affiliate disclosure did: routes/bhav.py cannot import routes/product.py (that
is the circular import product.py's own comments warn about), and four sections
printing four slightly different disclaimers is how one of them quietly stops
saying the thing that matters. Nothing in services/ imports routes/, so every
section can reach this.

What these sentences deliberately do NOT do:

  * promise a product works, or name a dose — that would be the advice we are
    saying we do not give (see tools/articles' advisory detector for the same
    line held on the article side);
  * disclaim something we DO control. Our own price estimate is still labelled
    अनुमानित by the section's own wording, and the affiliate commission is
    still disclosed. A notice that tries to sign away everything is worth
    nothing when it matters, and reads as a warning to stay away.
  * scare a farmer off the page. Two sentences, in the same plain Hindi as the
    rest of the notice, at the bottom of a box he is already reading.
"""

import re

# ── Inputs a farmer buys: बीज, खाद, कीटनाशक, पशु आहार ───────
SAFETY_INPUTS = (
    "दवा, खाद या कीटनाशक इस्तेमाल करने से पहले पैक पर लिखा लेबल, मात्रा और "
    "चेतावनी ज़रूर पढ़ें, दस्ताने-मास्क पहनें, और शक हो तो कृषि विभाग / KVK या "
    "किसी जानकार से पूछ लें। यहाँ दी जानकारी सामान्य जानकारी है — आपकी फसल, "
    "खेत या पशु के लिए सिफ़ारिश नहीं।"
)

NO_LIABILITY_GOODS = (
    "सामान की क्वालिटी, असली-नकली और असर की ज़िम्मेदारी बनाने वाली कंपनी और "
    "दुकानदार की है। सामान के इस्तेमाल या खरीद से फसल, पशु, सेहत या पैसे के "
    "किसी भी नुकसान के लिए कृषि मित्र ज़िम्मेदार नहीं है।"
)

# The two together, in the order they are always printed — so a section adds
# one name to its notice instead of remembering two.
#
# The ⚠️ marker is load-bearing, not decoration: with it appended the /product
# notice is ten lines of Hindi in one yellow box at 390px, and a farmer skims
# a wall like that as one blob. The marker gives the eye somewhere to break,
# and it keeps the whole notice a single string — which is what lets every
# section (and the tests that guard them) treat it as one thing.
_CAUTION = "⚠️ सावधानी: "

GOODS_NOTE = f"{_CAUTION}{SAFETY_INPUTS} {NO_LIABILITY_GOODS}"

# ── Machines a farmer hires ─────────────────────────────────
# Same stance, different nouns: a rotavator does not have an expiry date, it
# has a guard that may be missing. The risk here is an accident, not a spray.
SAFETY_MACHINE = (
    "मशीन लेने से पहले उसकी हालत, गार्ड, ब्रेक और कागज़ जाँच लें; चलाने वाले की "
    "ट्रेनिंग और सुरक्षा का ध्यान रखना ज़रूरी है।"
)

NO_LIABILITY_MACHINE = (
    "मशीन, सौदा और उसका इस्तेमाल मालिक और किराये पर लेने वाले के बीच है — किसी "
    "दुर्घटना, खराबी या नुकसान के लिए कृषि मित्र ज़िम्मेदार नहीं है।"
)

MACHINE_NOTE = f"{_CAUTION}{SAFETY_MACHINE} {NO_LIABILITY_MACHINE}"

# ── The one-line version ────────────────────────────────────
# For a place with no notice box of its own: the affiliate shelf on /bhav's
# district pages, which lists a neem-oil pesticide beside a wheat price and
# has room for one line of fine print, not four.
SHELF_CAUTION = (
    "⚠️ दवा या कीटनाशक इस्तेमाल से पहले लेबल और मात्रा ज़रूर पढ़ें — सामान और उसके "
    "असर की ज़िम्मेदारी कृषि मित्र की नहीं है।"
)


# ── Doses (LEGAL_RULES §2) ──────────────────────────────────
# "We never author a pesticide, fertiliser or veterinary dose. We send the
# farmer to the product label, कृषि विभाग or KVK, or a registered vet."
#
# These three sentences are what stands where a number used to. Every surface
# that would otherwise print a quantity — the AI chat, the articles, the /khoj
# knowledge base, the crop calendar — says one of these instead, in this
# wording. The JSON and JS data files cannot import Python, so they carry the
# same sentences as text; tests/test_no_authored_doses.py holds all of it to
# having no dose left at all.
DOSE_PESTICIDE = (
    "मात्रा और छिड़काव का तरीका दवा के पैक पर छपे लेबल से लें, या अपने KVK / "
    "कृषि विभाग से पूछें।"
)
DOSE_FERTILISER = (
    "कितनी खाद डालनी है, यह अपने खेत के मृदा स्वास्थ्य कार्ड (Soil Health Card) "
    "की सिफ़ारिश से तय करें, या अपने KVK / कृषि विभाग से पूछें।"
)
DOSE_VET = "पशु की दवा और उसकी मात्रा पंजीकृत पशु चिकित्सक ही बताएँ।"
# For a line with no room for a sentence: a crop-calendar task, a table cell.
DOSE_SHORT = "(मात्रा: मृदा स्वास्थ्य कार्ड / पैक का लेबल / KVK के अनुसार)"
DOSE_SHORT_LABEL = "(मात्रा: दवा के पैक का लेबल / KVK से)"

# A quantity next to a rate unit: "2 ग्राम प्रति लीटर", "400-500 मिली/एकड़",
# "20 ಕೆಜಿ ಪ್ರತಿ ಎಕರೆ", "2 கிராம் ஒரு லிட்டர்", "120 kg per hectare" — and the
# two reversed orders a Hindi sentence also uses: "प्रति एकड़ 50 किलो" and
# "15 लीटर पानी में 30 मिली". Moved here from tools/article_advisory.py (which
# re-exports it) so the chat, the article builder and the tests share one
# definition. It also matches a seed rate ("40 किलो प्रति एकड़"): the surfaces
# that must print one say it without a per-unit number ("एक एकड़ में 40 किलो
# बीज"), which is the cheaper price for a detector that never misses a dose.
_AMOUNT = (r"(?:ग्राम|ग्रा\.?|मिलीलीटर|मिली|मि\.?ली\.?|किलोग्राम|किलो|किग्रा|"
           r"केजी|लीटर|एमएल|मिलीग्राम|क्विंटल|बोरी|टन|"
           r"ಗ್ರಾಂ|ಮಿಲಿ|ಮಿ\.?ಲಿ\.?|ಕೆಜಿ|ಕೆ\.ಜಿ\.?|ಕಿ\.?ಗ್ರಾ\.?|ಗ್ರಾ\.?|ಕಿಲೋ|ಲೀಟರ್|ಟನ್|"
           r"கிராம்|மில்லி|கிலோ|லிட்டர்|"
           r"ml|gm|kg|g|l|tons?|tonnes?)")
_PER = r"(?:/|प्रति|ಪ್ರತಿ|ஒரு|per)"
_BASE = (r"(?:लीटर|ली\.?|l|L|kg|पानी|एकड़|हेक्टेयर|हे\.?|बीघा|बीघे|पंप|टंकी|किलोग्राम|किलो|किग्रा|"
         r"बीज|बोरी|पेड़|पौधा|पौधे|गड्ढा|गड्ढे|पशु|"
         r"ಲೀಟರ್|ಲೀ\.?|ಎಕರೆ|ಎಕರೆಗೆ|ಹೆಕ್ಟೇರ್|ನೀರು|ಬೀಜ|ಕೆಜಿ|ಕಿ\.?ಗ್ರಾ\.?|ಗಿಡ|ಗಿಡಕ್ಕೆ|"
         r"லிட்டர்|ஏக்கர்|ஹெக்டேர்|தண்ணீர்|விதை|"
         r"litre|liter|acre|ha|hectare)")
# "Not followed by more of a word" — the unit must end where the word ends
# ("ha" is not "hai"). । and ॥ are in the Devanagari block but end a sentence,
# so they are carved out: "25 kg प्रति एकड़।" is a dose.
_END = r"(?![\w\u0900-\u0963\u0966-\u097F])"
_KN_PER = r"(?:ಎಕರೆಗೆ|ಹೆಕ್ಟೇರಿಗೆ|ಹೆಕ್ಟೇರ್‌ಗೆ|ಗಿಡಕ್ಕೆ)"
_PERN = r"(?:\d+(?:[.,]\d+)?\s*)?"
_NUM = r"\d+(?:[.,]\d+)?\s*(?:(?:-|–|से|to)\s*\d+(?:[.,]\d+)?\s*)?"
DOSE_RE = re.compile(
    "|".join((
        # up to a few words between amount and rate: "25 किग्रा जिंक सल्फेट/हे"
        # "per 10 litres" is still per: "3 मि.ली. प्रति 10 लीटर पानी", "/15 लीटर पंप"
        _NUM + _AMOUNT + _END + r"[^।;,.\n\d()]{0,30}?" + _PER + r"\s*" + _PERN + _BASE + _END,
        # "प्रति एकड़ 50 किलो", "Per acre: N-50kg"
        _PER + r"\s*" + _PERN + _BASE + _END + r"\s*:?\s*(?:[A-Za-z]{1,3}\s*[-–:]\s*)?"
        + r"(?:(?:लगभग|करीब|क़रीब|about|approx\.?|around|ಸುಮಾರು)\s*)?"
        + _NUM + _AMOUNT + _END,
        _NUM + r"(?:लीटर|ली\.?|litre|liter|l)\s*(?:पानी|गोमूत्र)(?:</strong>)?\s*में\s*" + _NUM + _AMOUNT
        + _END,
        # fumigant tablets in a store: "1 गोली प्रति क्विंटल", "1 गोली/टन"
        _NUM + r"(?:गोली|गोलियाँ|टैबलेट|tablets?)" + _END + r"\s*" + _PER + r"\s*"
        + r"(?:क्विंटल|टन|ton|tonne|quintal)" + _END,
        # Kannada says "per acre" with a case ending, not a separate word:
        # "ಎಕರೆಗೆ 10 ಕೆಜಿ", "ಎಕರೆಗೆ: ಸಾರಜನಕ 50 ಕಿ.ಗ್ರಾ", "10 ಕೆಜಿ/ಎಕರೆಗೆ"
        _KN_PER + r"\s*:?[^।;.\n\d]{0,30}?" + _NUM + _AMOUNT + _END,
        _NUM + _AMOUNT + _END + r"[^।;.\n\d]{0,30}?" + _KN_PER,
    )), re.I)

_REDACT = {
    "hi": "लेबल / KVK वाली मात्रा",
    "en": "the dose on the label / from your KVK",
    "kn": "ಲೇಬಲ್ / KVK ಹೇಳುವ ಪ್ರಮಾಣ",
}
_REFERRAL = {
    "hi": f"{DOSE_PESTICIDE} {DOSE_FERTILISER}",
    "en": ("Take the dose from the product label or your Soil Health Card, "
           "or ask your KVK / agriculture department."),
    "kn": ("ಪ್ರಮಾಣವನ್ನು ಉತ್ಪನ್ನದ ಲೇಬಲ್ ಅಥವಾ ಮಣ್ಣು ಆರೋಗ್ಯ ಕಾರ್ಡ್‌ನಿಂದ ತೆಗೆದುಕೊಳ್ಳಿ, "
           "ಅಥವಾ ನಿಮ್ಮ KVK / ಕೃಷಿ ಇಲಾಖೆಯನ್ನು ಕೇಳಿ."),
}


def find_doses(text: str) -> list[str]:
    """Every quantity-per-unit expression in `text`."""
    return [re.sub(r"\s+", " ", m.group(0)) for m in DOSE_RE.finditer(text or "")]


def redact_doses(text: str, lang: str = "hi") -> str:
    """The last line of defence for text we did not write word by word.

    The AI chat is told never to give a dose, and its saved answers were
    cleaned — but a model can still slip, and a cached answer is served
    verbatim. Every figure DOSE_RE finds becomes "लेबल / KVK वाली मात्रा", and
    the referral sentence is added once, so the answer still reads as a
    sentence and still tells the farmer where the number lives.
    """
    lang = lang if lang in _REDACT else "hi"
    out, n = DOSE_RE.subn(_REDACT[lang], text or "")
    if n and _REFERRAL[lang] not in out:
        out = f"{out.rstrip()}\n{_REFERRAL[lang]}"
    return out
