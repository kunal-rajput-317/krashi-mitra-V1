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
