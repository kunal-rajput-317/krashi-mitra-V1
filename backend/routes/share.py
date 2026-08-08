# ============================================================
# routes/share.py
# Krishi Mitra — Rich link previews for shared mandi links
#
# WhatsApp/Facebook/Telegram crawlers read OG tags from the first
# 200 response and do NOT follow meta-refresh, so this page carries
# the crop-specific preview while humans get bounced to /bhav.
# Reached via the Netlify proxy rule /share/* → backend.
# ============================================================

import re
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.services.mandi_service import get_mandi_prices
from backend.database.db import BazarPost, User, UserProfile, get_db, acct

router = APIRouter()

SITE = "https://krashimitra.in"
BACKEND = "https://krashi-mitra-v1-oxdc.onrender.com"

# commodity keyword → (Wikimedia file, md5 prefix)
# same ordering the /bhav hub's photo-card grid uses
#
# Two blocks. These are the STAPLES: the crops the app's mandi grid leads with,
# and — because _tile_rank() is just the index here — the order the /bhav hub's
# photo-card grid opens in. The long-tail block below adds photos for the rest
# of Agmarknet's ~300 commodities WITHOUT joining that grid; see _STAPLE_TILES_N.
_STAPLE_TILES = [
    (("wheat",),                    "Wheat close-up.JPG",                        "b4"),
    (("paddy", "dhan", "rice"),     "Rice_grains_(IRRI).jpg",                    "ba"),
    (("onion",),                    "Onion on White.JPG",                        "25"),
    (("potato",),                   "Patates.jpg",                               "ab"),
    (("tomato",),                   "Bright red tomato and cross section02.jpg", "88"),
    (("maize", "corn"),             "Corncobs.jpg",                              "7d"),
    (("soyabean", "soybean"),       "Soybean.USDA.jpg",                          "82"),
    (("gram", "chana", "bengal"),   "Chickpea.jpg",                              "3d"),
    (("mustard", "rai", "sarson"),  "BrownMustardSeed.JPG",                      "ef"),
    (("garlic",),                   "Garlic.jpg",                                "22"),
    (("chilli", "chili", "mirch"),  "Red Chili Pepper.jpg",                      "2a"),
    (("turmeric",),                 "Turmeric-powder.jpg",                       "0a"),
    (("groundnut",),                "Groundnut (Arachis hypogaea).jpg",          "0e"),
    (("bajra", "pearl millet"),     "Bajra.JPG",                                 "49"),
    (("arhar", "tur", "red gram"),  "Toor dal.jpg",                              "de"),
    (("urad", "black gram"),        "Vigna mungo.jpg",                           "e2"),
    (("moong", "green gram"),       "Mung_beans.jpg",                            "5e"),
    (("sugarcane",),                "Sugar cane.jpg",                            "cb"),
    (("cotton",),                   "CottonPlant.JPG",                           "68"),
    (("lentil", "masur", "masoor"), "Lentil.jpg",                                "9d"),
    (("peas", "pea"),               "Green peas.jpg",                            "a7"),
    (("brinjal",),                  "Aubergine.jpg",                             "fb"),
    (("cauliflower",),              "Cauliflower.jpg",                           "7c"),
    (("ginger",),                   "Ginger root.jpg",                           "cf"),

    # The md5 prefix is the first two hex chars of md5(filename with underscores) —
    # it is the CDN shard, not a label, so a guessed value 404s every thumb.
    (("bhindi", "ladies finger", "okra"),      "Okra.jpg",                       "90"),
    (("banana",),                              "Bananas.jpg",                    "4c"),
    (("bitter gourd", "karela"),               "Bitter_melon.jpg",               "63"),
    (("cucumber", "kheera"),                   "Cucumbers.jpg",                  "77"),
    (("bottle gourd", "lauki"),                "Bottle_gourd.jpg",               "08"),
    (("cabbage", "patta gobhi"),               "Cabbage.jpg",                    "70"),
    (("pumpkin", "kaddu"),                     "Pumpkin.jpg",                    "f7"),
    (("mango", "aam"),                         "Mango_fruit.jpg",                "64"),
    (("lemon", "nimbu"),                       "Lemon.jpg",                      "e4"),
    (("carrot", "gajar"),                      "Carrots.jpg",                    "c8"),
    (("ridgeguard", "tori"),                   "Luffa_acutangula.jpg",           "59"),
    (("coriander", "dhaniya"),                 "Coriander.jpg",                  "1b"),
    (("raddish", "radish", "mooli"),           "Radish.jpg",                     "03"),
    (("papaya", "papita"),                     "Papaya_fruit.jpg",               "99"),
    (("capsicum", "shimla mirch"),             "Capsicum.jpg",                   "73"),
    (("drumstick", "moringa", "sahjan"),       "Moringa_oleifera.jpg",           "f1"),
    (("coconut", "nariyal"),                   "Coconut.jpg",                    "26"),
    (("apple", "seb"),                         "Apple.jpg",                      "2b"),
    (("mint", "pudina"),                       "Mint_leaves.jpg",                "ce"),
    (("guava", "amrood"),                      "Guava_fruit.jpg",                "d6"),
    (("jowar", "sorghum"),                     "Sorghum seed.jpg",               "2a"),
    (("mousambi", "sweet lime"),               "Sweet limes of Salem.jpg",       "77"),
    (("pomegranate", "anar"),                  "Pomegranate.jpg",                "5d"),
    (("sesamum", "sesame", "til"),             "Yonghui preferred white sesame seeds.jpg", "65"),
    (("watermelon", "water melon", "tarbooz"), "Watermelon.jpg",                 "b9"),
    (("spinach", "palak"),                     "Spinach.jpg",                    "cd"),
    (("grapes", "angoor"),                     "Grapes.jpg",                     "6b"),
    (("barley", "jau"),                        "Barley.jpg",                     "e0"),
    (("orange", "santra"),                     "Oranges - whole-halved-segment.jpg", "e3"),
    (("cumin", "jeera"),                       "Cumin seed.jpg",                 "17"),
]

# ── Long tail ────────────────────────────────────────────────────────────────
# Everything else Agmarknet reports. Before this block 207 of the 309 /bhav crop
# pages had no photo at all: the hub chip fell back to a 🌾 glyph, the crop card
# and the tier-3 answer photo were omitted outright, and og:image was the generic
# site banner — so every one of those pages shared one social preview.
#
# KEYWORDS ARE SINGLE TOKENS on purpose. _slugify() collapses every run of
# punctuation to "-", so a slug like "ber-zizyphus-borehannu" comes from
# "Ber(Zizyphus/Borehannu)" — the phrase "ber zizyphus" never appears in the raw
# name and a multi-word keyword would silently never match. Each individual token
# always does, bounded by the punctuation around it. The two "tube ..." rows are
# the deliberate exception: they need the second word to outrank bare "rose".
#
# Files and md5 shards are machine-derived, not hand-typed: each filename is a
# real Commons file resolved through the Wikipedia/Commons API, and the shard is
# md5(filename with underscores)[:2] — the same formula reproduces all 54 prefixes
# in the staple block above, and every URL below was fetched and confirmed to
# return image bytes.
_LONGTAIL_TILES = [
    # spices, herbs & medicinal
    (("absinthe",),               "Artemisia absinthium P1210748.jpg",              "eb"),
    (("ajwan",),                  "Carom Flowers.jpg",                              "a6"),
    (("akarkara",),               "Anacyclus pyrethrum kz03.jpg",                   "18"),
    (("asalia",),                 "Lepidium sativum 2019-05-04 2820.jpg",           "2d"),
    (("asgand",),                 "WithaniaFruit.jpg",                              "ad"),
    (("ashwagandha",),            "WithaniaFruit.jpg",                              "ad"),
    (("basil",),                  "Ocimum basilicum 8zz.jpg",                       "97"),
    (("tejpatta",),               "Bay Leaves.JPG",                                 "a8"),
    (("behada",),                 "Terminalia bellirica.jpg",                       "74"),
    (("pepper",),                 "Pimienta negra (Piper nigrum), 2020-06-12, DD 20-40 FS.jpg", "e5"),
    (("cardamom",),               "02017 0119 Kardamom, Winter in den Beskiden.jpg", "66"),
    (("chiaseeds",),              "Seed of chia (Salvia hispanica)Salvia hispanica group.jpg", "2f"),
    (("chicory",),                "Cichorium intybus-alvesgaspar1.jpg",             "80"),
    (("dalchini", "cinamon"),     "Cinnamomum verum spices.jpg",                    "de"),
    (("corriander",),             "Coriander Seeds.jpg",                            "86"),
    (("chillies",),               "Red Chili Pepper.jpg",                           "2a"),
    (("giloy",),                  "Tinospora cordifolia.jpg",                       "0e"),
    (("gokhru",),                 "Tribulus terrestris (Family Zygophyllaceae).jpg", "8a"),
    (("gond",),                   "Gum Arabic exuding.jpg",                         "79"),
    (("isabgul", "psyllium"),     "Plantago afra kz6.jpg",                          "bf"),
    (("mahedi",),                 "Henna on foot in Morocco.jpg",                   "17"),
    (("mentha",),                 "Mentha spicata-IMG 6186.jpg",                    "4d"),
    (("methi",),                  "Trigonella foenum-graecum-1-yercaud-salem-India.JPG", "11"),
    (("muleti",),                 "Sections of liquorice root.jpg",                 "57"),
    (("neem",),                   "Neem Tree in Rajasthan, India.jpg",              "7b"),
    (("nigella",),                "Nsativa001Wien.jpg",                             "53"),
    (("poppy",),                  "Poppy seeds.jpg",                                "69"),
    (("saffron",),                "Saffron - premium spice.jpg",                    "68"),
    (("soanf",),                  "Foeniculum July 2011-1a.jpg",                    "c0"),
    (("soapnut", "antawala"),     "Sapindus marginatus.jpg",                        "8d"),
    (("suva",),                   "Dill seed.JPG",                                  "d6"),
    (("tamarind",),               "Tamarindus indica pods.JPG",                     "2e"),
    (("tendu", "kendu"),          "Tendu tree.jpg",                                 "af"),
    (("tobacco",),                "Dried Tobacco Leaves.jpg",                       "b2"),
    (("muesli",),                 "Chlorophytum borivilianum (4695984110).jpg",     "7f"),

    # fruit
    (("almond", "badam"),         "Almonds - in shell, shell cracked open, shelled, blanched.jpg", "37"),
    (("amla",),                   "Phyllanthus officinalis.jpg",                    "7f"),
    (("apricot",),                "Apricot and cross section.jpg",                  "2a"),
    (("avocado",),                "Persea americana fruit 2.JPG",                   "f2"),
    (("zizyphus", "borehannu"),   "Indian jujube (fruit).jpg",                      "fc"),
    (("blueberry",),              "Blueberries.jpg",                                "15"),
    (("cashewnuts",),             "Cashew apples.jpg",                              "64"),
    (("cherry",),                 "Cherry season (48216568227).jpg",                "f6"),
    (("sapota", "chikoos"),       "സപ്പോട്ട.jpg",                                    "00"),
    (("anjeer", "anjura"),        "Ficus Carica.jpg",                               "6a"),
    (("jack", "jackfruit"),       "The jackfruit is holding on to the tree.jpg",    "3b"),
    (("jamun",),                  "Syzygium cumini Bra30.png",                      "b3"),
    (("karbuja", "muskmelon"),    "Muskmelon Bangladeshi.jpg",                      "ec"),
    (("kinnow",),                 "Harvest Kinnow.jpg",                             "c9"),
    (("kiwi",),                   "Actinidia fruits.jpg",                           "0a"),
    (("lime",),                   "Lime Blossom.jpg",                               "8b"),
    (("litchi",),                 "Litchi chinensis fruits.JPG",                    "46"),
    (("kakri",),                  "Cucumis melo flexuosus.jpg",                     "0b"),
    (("peach",),                  "Autumn Red peaches.jpg",                         "9e"),
    (("pear",),                   "Pears.jpg",                                      "cf"),
    (("pineapple",),              "കൈതച്ചക്ക.jpg",                                   "74"),
    (("plum",),                   "Plums African Rose - whole, halved and slice.jpg", "ec"),
    (("ramphal",),                "Custard Apple (Annona reticulata) in Maharashtra, India.jpg", "60"),
    (("seetapal",),               "Sugar apple on tree.jpg",                        "42"),

    # vegetables & gourds
    (("ashgourd",),               "Benincasa hispida compose.jpg",                  "d2"),
    (("asparagus",),              "Asparagus-Bundle.jpg",                           "3d"),
    (("beetroot",),               "Detroitdarkredbeets.png",                        "ae"),
    (("chow",),                   "Chayote BNC.jpg",                                "f1"),
    (("seemebadnekai",),          "Chayote BNC.jpg",                                "f1"),
    (("colacasia",),              "Songe-Réunion.JPG",                              "30"),
    (("arvi",),                   "Songe-Réunion.JPG",                              "30"),
    (("suran",),                  "Amorphophallus Paeoniifolius g.jpg",             "61"),
    (("suvarna",),                "Amorphophallus Paeoniifolius g.jpg",             "61"),
    (("knool",),                  "Brassica oleracea var. gongylodes (kohlrabi).jpg", "98"),
    (("leafy",),                  "Spinach leaves.jpg",                             "fe"),
    (("kundru",),                 "Coccinia grandis fruit.jpg",                     "e9"),
    (("thondekai",),              "Coccinia grandis fruit.jpg",                     "e9"),
    (("mashrooms",),              "Edible fungi in basket 2009 G1 (cropped).jpg",   "18"),
    (("parval",),                 "Pointed gourd.jpg",                              "2d"),
    (("permal",),                 "Luffa acutangula.jpg",                           "59"),
    (("round",),                  "Tinda.jpg",                                      "80"),
    (("tinda",),                  "Tinda.jpg",                                      "80"),
    (("snakeguard",),             "Trichosanthes cucumerina var. anguina compose.jpg", "cb"),
    (("kantola", "kartali"),      "Erumapaval.JPG",                                 "86"),
    (("sponge",),                 "Luffa aegyptiaca compose.jpg",                   "18"),
    (("squash",),                 "Squashes at Kew Gardens IncrEdibles 2013.jpg",   "ea"),
    (("tapioca",),                "Freshly harvested cassava roots in a yellow basin.png", "16"),
    (("turnip",),                 "Turnip 2622027.jpg",                             "d3"),
    (("yam",),                    "Yam at monday market kaduna state 01.jpg",       "72"),
    (("ratalu",),                 "Kambar wh.jpg",                                  "4a"),
    (("betal",),                  "Piper betle plant.jpg",                          "99"),
    (("makhana",),                "Junicho-Gata lagoon Euryale feroxe habitat 07.jpg", "25"),
    (("lotus",),                  "Sacred lotus Nelumbo nucifera.jpg",              "ed"),
    (("vegetables",),             "Marketvegetables.jpg",                           "24"),

    # pulses & beans
    (("alsandikai",),             "Lobia.jpg",                                      "08"),
    (("cowpea",),                 "Lobia.jpg",                                      "08"),
    (("avare",),                  "Hyacinth bean (Lablab purpureus) flower and pods in Bangladesh.jpg", "60"),
    (("anumulu",),                "Hyacinth bean (Lablab purpureus) flower and pods in Bangladesh.jpg", "60"),
    (("seam",),                   "Hyacinth bean (Lablab purpureus) flower and pods in Bangladesh.jpg", "60"),
    (("papadi",),                 "Hyacinth bean (Lablab purpureus) flower and pods in Bangladesh.jpg", "60"),
    (("cluster",),                "Cluster bean.jpg",                               "f3"),
    (("duster",),                 "Cluster bean.jpg",                               "f3"),
    (("guar",),                   "Cluster bean.jpg",                               "f3"),
    (("rajma",),                  "Red Rajma BNC.jpg",                              "27"),
    (("bunch",),                  "Heaps of beans.jpg",                             "a0"),
    (("frasbean",),               "Heaps of beans.jpg",                             "a0"),
    (("mataki",),                 "Matki.JPG",                                      "2f"),
    (("teora",),                  "Lathyrus sativus flowers Bangladesh cropped.JPG", "ae"),
    (("dal",),                    "3 types of lentil.png",                          "f5"),
    (("pulses",),                 "Various legumes.jpg",                            "e7"),

    # cereals, millets & oilseeds
    (("chena",),                  "Mature Proso Millet Panicles.jpg",               "40"),
    (("navane", "thinai"),        "Japanese Foxtail millet 02.jpg",                 "9a"),
    (("kodo", "varagu"),          "Paspalum scrobiculatum 224164066.jpg",           "fd"),
    (("kutki",),                  'A crop "samai " grown in the rain water only itself.jpg', "99"),
    (("savi",),                   'A crop "samai " grown in the rain water only itself.jpg', "99"),
    (("ragi",),                   "Finger millet 3 11-21-02.jpg",                   "6c"),
    (("cumbu",),                  "Bajra.JPG",                                      "49"),
    (("millets",),                "Grain millet, early grain fill, Tifton, 7-3-02.jpg", "f0"),
    (("jaee",),                   "AvenaSativa3.jpg",                               "f0"),
    (("quinoa",),                 "Reismelde.jpg",                                  "96"),
    (("amaranthus",),             "Amaranthus tricolor0.jpg",                       "91"),
    (("rajgir",),                 "Amaranthus tricolor0.jpg",                       "91"),
    (("amranthas",),              "Amaranthus cruentus1.jpg",                       "05"),
    (("maida",),                  "Maida flour.jpg",                                "49"),
    (("castor",),                 "Ricinus March 2010-1.jpg",                       "f7"),
    (("flax", "linseed"),         "Flaxseed.jpg",                                   "f5"),
    (("ground",),                 "Groundnut (Arachis hypogaea).jpg",               "0e"),
    (("gurellu",),                "Guizotia abyssinica niger.jpg",                  "74"),
    (("ramtil",),                 "Guizotia abyssinica niger.jpg",                  "74"),
    (("karanja",),                "Pongamia pinnata (Karanj) near Hyderabad W IMG 7633.jpg", "1b"),
    (("safflower",),              "Safflower.jpg",                                  "7f"),
    (("sunflower",),              "Sunflower sky backdrop.jpg",                     "40"),
    (("taramira",),               "Eruca sativa II.jpg",                            "22"),
    (("rayee",),                  "BrownMustardSeed.JPG",                           "ef"),
    (("muskmallow", "ambrette"),  "Abelmoschus moschatus DSC 4408.jpg",             "87"),

    # plantation, processed & sugar
    (("arecanut",),               "Areca nut garden (3).jpg",                       "b5"),
    (("betelnuts",),              "Areca nut garden (3).jpg",                       "b5"),
    (("cocoa",),                  "Cocoa Pods.JPG",                                 "e0"),
    (("coffee",),                 "Roasted coffee beans.jpg",                       "c5"),
    (("copra",),                  "Kerala coconut.jpg",                             "d5"),
    (("jaggery",),                "Sa-indian-gud.jpg",                              "09"),
    (("molasses",),               "Blackstrapmolasses.JPG",                         "8f"),
    (("khandsari",),              "Sucre blanc cassonade complet rapadura.jpg",     "3c"),
    (("sugar",),                  "Sucre blanc cassonade complet rapadura.jpg",     "3c"),
    (("sabu",),                   "Dried sago pearls.jpg",                          "b2"),
    (("ghee",),                   "Pure Ghee.jpg",                                  "61"),
    (("rubber",),                 "Caoutchouc naturel.jpg",                         "42"),
    (("jute",),                   "Jute - Kolkata 2003-10-31 00538.JPG",            "84"),
    (("lint",),                   "CottonPlant.JPG",                                "68"),
    (("bamboo",),                 "Bamboo forest.jpg",                              "f3"),
    (("broomstick",),             "अम्रिसो.jpg",                                     "b4"),

    # flowers
    (("anthorium",),              "Anthurium3.JPG",                                 "75"),
    (("astera",),                 "Asterales - Callistephus chinensis - 20120823.jpg", "08"),
    (("carnation",),              "W carnation4051.jpg",                            "3b"),
    (("chrysanthemum",),          "Chrysanthemum flowers yellow.jpg",               "fe"),
    (("gladiolus",),              "0 Gladiolus italicus - Samoëns (1).JPG",         "45"),
    (("jarbara",),                "Unidentified Gerbera.jpg",                       "3b"),
    (("jasmine",),                "Common Jasmine.jpg",                             "42"),
    (("raibel",),                 "Arabian jasmin, Tunisia 2010.jpg",               "f3"),
    (("kakada",),                 "Crape Jasmine.jpg",                              "da"),
    (("kankambra",),              "Crossandra infundibuliformis kanakambaram Madhurawada Visakhapatnam.JPG", "b9"),
    (("lilly",),                  "Lilium candidum 1.jpg",                          "30"),
    (("marigold",),               "Tagetes erecta 26122014 (3).jpg",                "8d"),
    (("orchid",),                 "Plant Orchid Cymbidium aloifolium P1110661 05 - cropped.jpg", "34"),
    (("rose",),                   "Rosa rubiginosa 1.jpg",                          "e6"),
    # "tube rose"/"tube flower" must beat bare "rose" — the only multi-word
    # keywords here, and safe because Agmarknet space-separates both names.
    (("tube rose",),              "Tuberose flower.jpg",                            "8e"),
    (("tube flower",),            "Clerodendrum indicum inflorescence.jpg",         "2a"),
    (("tulip",),                  "צבעונים.JPG",                                    "9e"),
    (("amaltas",),                "Golden shower tree.jpg",                         "f9"),
    (("rambans",),                "Agave July 2011-1.jpg",                          "3b"),

    # trees, fodder & green manure
    (("baboolphali",),            "Macro view of thorn and leaves of a Babul tree (Vachellia nilotica) from Rajasthan, India.jpg", "6a"),
    (("dhaincha",),               "Sesbania bispinosa5836.JPG",                     "d4"),
    (("mahua",),                  "Mahuwa trees in Chhattisgarh.jpg",               "61"),
    (("fodder",),                 "Fodder factory02.jpg",                           "08"),

    # livestock & animal produce — these keep their own /bhav pages, so they
    # need a photo for the same reason the crops do
    (("cow",),                    "Cow (Fleckvieh breed) Oeschinensee Slaunger 2009-07-07.jpg", "8c"),
    (("ox",),                     "India.Mumbai.04.jpg",                            "09"),
    (("buffalo",),                "Water buffalo at Rinca.jpg",                     "bc"),
    (("goat",),                   "Hausziege 04.jpg",                               "b2"),
    (("sheep",),                  "Flock of sheep.jpg",                             "2c"),
    (("pigs",),                   "Pig farm Vampula 1.jpg",                         "3e"),
    (("egg",),                    "Huevo frito.jpg",                                "3f"),
    (("fish",),                   "Fresh fish in market (27002392530).jpg",         "fb"),
    (("prawn",),                  "Penaeus monodon.jpg",                            "98"),

    # LAST ON PURPOSE. _crop_image() breaks ties by first-match, so the generic
    # "beans" must sit behind the equally-long "rajma" and "bunch" or
    # "Kidney Beans(Rajma)" would take the plain French-bean photo.
    (("beans",),                  "French beans J1.JPG",                            "a0"),
]

_TILES = _STAPLE_TILES + _LONGTAIL_TILES

# Where the staples end. The /bhav hub uses this — not len(_TILES) — to decide
# which crops lead the page as photo cards, so adding a long-tail photo gives a
# crop its picture in the chip list without promoting it into the hero grid.
_STAPLE_TILES_N = len(_STAPLE_TILES)

_FALLBACK_IMAGE = f"{SITE}/images/og-banner.webp"


# Wikimedia only serves whitelisted thumb widths (https://w.wiki/GHai) —
# verified working: 330, 500, 960, 1280. Anything else returns HTTP 400.
_ALLOWED_WIDTHS = (330, 500, 960, 1280)

# Thumbs wider than the original also 400 — originals narrower than 960px
# (checked via the Commons imageinfo API); everything else is ≥ 960 wide.
_MAX_ORIG_WIDTH = {
    "Chickpea.jpg":     350,
    "Soybean.USDA.jpg": 640,
    "Aubergine.jpg":    681,
    "Cauliflower.jpg":  909,
    "Radish.jpg":       579,
    "Cabbage.jpg":      640,
    "Barley.jpg":       640,
    "Coriander.jpg":    800,

    # long-tail files (widths read from the Commons imageinfo API, not guessed)
    "Amaranthus cruentus1.jpg":                          640,
    "Amaranthus tricolor0.jpg":                          640,
    "Asterales - Callistephus chinensis - 20120823.jpg": 600,
    "Bamboo forest.jpg":                                 720,
    "Blueberries.jpg":                                   640,
    "India.Mumbai.04.jpg":                               640,
    "Kerala coconut.jpg":                                800,
    "Lathyrus sativus flowers Bangladesh cropped.JPG":   807,
    "Lobia.jpg":                                         800,
    "Mahuwa trees in Chhattisgarh.jpg":                  759,
    "Matki.JPG":                                         400,
    "Pears.jpg":                                         640,
    "Phyllanthus officinalis.jpg":                       640,
    "Pongamia pinnata (Karanj) near Hyderabad W IMG 7633.jpg": 608,
    "Reismelde.jpg":                                     792,
    "Safflower.jpg":                                     500,
    "Tamarindus indica pods.JPG":                        768,
    "Terminalia bellirica.jpg":                          640,
    "Tinda.jpg":                                         388,
    "Trichosanthes cucumerina var. anguina compose.jpg": 895,
    "Various legumes.jpg":                               640,
    "W carnation4051.jpg":                               800,
}


def _crop_image(commodity: str, width: int = 330) -> str:
    """Photo for a commodity, matched on WHOLE WORDS and by the MOST SPECIFIC
    keyword. Plain substring matching gave "Turnip" the अरहर photo ("tur") and
    "Peach"/"Pear" the मटर photo ("pea"); first-tile-wins gave "Green Gram(Moong)"
    the चना photo, because the generic "gram" tile is listed before "green gram"."""
    cl = (commodity or "").lower()
    best, best_len = None, 0
    for keys, file, h in _TILES:
        for k in keys:
            if re.search(rf"\b{re.escape(k)}\b", cl) and len(k) > best_len:
                best, best_len = (file, h), len(k)
    if best:
        file, h = best
        cap = min(width, _MAX_ORIG_WIDTH.get(file, 10**6))
        w = max([a for a in _ALLOWED_WIDTHS if a <= cap] or [330])
        n = quote(file.replace(" ", "_"))
        return (
            "https://upload.wikimedia.org/wikipedia/commons/thumb/"
            f"{h[0]}/{h}/{n}/{w}px-{n}"
        )
    return _FALLBACK_IMAGE


# Hindi crop names used by Krashi Bazar chips → English keyword for _crop_image()
_HI_CROP_EN = {
    "गेहूं": "wheat", "धान": "paddy", "सोयाबीन": "soybean", "प्याज": "onion",
    "आलू": "potato", "टमाटर": "tomato", "मक्का": "maize", "सरसों": "mustard",
    "चना": "chana", "गन्ना": "sugarcane", "लहसुन": "garlic", "मिर्च": "chilli",
    "हल्दी": "turmeric", "मूंगफली": "groundnut", "अरहर": "arhar", "उड़द": "urad",
    "मूंग": "moong", "कपास": "cotton", "मसूर": "masur", "मटर": "peas",
    "बैंगन": "brinjal", "अदरक": "ginger",
    
    # ── 30 Additional Highly-Active Crops ──
    "भिंडी": "bhindi",
    "केला": "banana",
    "करेला": "bitter gourd",
    "खीरा": "cucumber",
    "लौकी": "bottle gourd",
    "पत्ता गोभी": "cabbage",
    "कद्दू": "pumpkin",
    "आम": "mango",
    "नींबू": "lemon",
    "गाजर": "carrot",
    "तोरई": "ridgeguard",
    "धनिया": "coriander",
    "मूली": "raddish",
    "पपीता": "papaya",
    "शिमला मिर्च": "capsicum",
    "सहजन": "drumstick",
    "नारियल": "coconut",
    "सेब": "apple",
    "पुदीना": "mint",
    "अमरूद": "guava",
    "ज्वार": "jowar",
    "मौसंबी": "mousambi",
    "अनार": "pomegranate",
    "तिल": "sesamum",
    "तरबूज": "watermelon",
    "पालक": "spinach",
    "अंगूर": "grapes",
    "जौ": "barley",
    "संतरा": "orange",
    "जीरा": "cumin",
}


@router.get("/share/bazar/{post_id}", response_class=HTMLResponse)
def share_bazar(post_id: int, db: Session = Depends(get_db)):
    """OG preview card for a Krashi Bazar post — photo + price + details."""
    target = f"{SITE}/krashi_bajar.html?post={post_id}"

    title = "कृषि बाज़ार — किसान से सीधे खरीदें व बेचें | कृषि मित्र"
    desc  = "फसल की फोटो/वीडियो, सीधा भाव और ऑफर — सीधे किसान से जुड़ें। KrashiMitra पर देखें।"
    image = _FALLBACK_IMAGE

    try:
        post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
        if post:
            user    = db.query(User).filter(User.id == post.user_id).first()
            profile = db.query(UserProfile).filter(UserProfile.user_id == acct(post.user_id)).first()

            name = (profile.name if profile and profile.name
                    else (user.name if user else "किसान"))
            tick = " ✅" if user and user.seller_verified else ""
            verb = "बेचना है" if post.post_type == "sell" else "खरीदना है"

            bits = [post.crop or "फसल", verb]
            if post.price:
                bits.append(f"₹{post.price:g}/{post.unit or 'क्विंटल'}")
            title = " — ".join(bits) + " | कृषि बाज़ार"

            dparts = []
            if post.quantity:
                dparts.append(f"📦 {post.quantity:g} {post.unit or 'क्विंटल'} उपलब्ध")
            if post.location:
                dparts.append(f"📍 {post.location}")
            dparts.append(f"🧑‍🌾 {name}{tick}")
            snippet = (post.text or "").strip()
            if snippet:
                dparts.append(snippet[:120] + ("…" if len(snippet) > 120 else ""))
            desc = " · ".join(dparts)

            if post.media_url and post.media_type == "image":
                image = f"{BACKEND}{post.media_url}"
            elif post.crop:
                en = _HI_CROP_EN.get(post.crop.strip(), post.crop)
                image = _crop_image(en, 960)
    except Exception:
        pass  # fall back to generic preview

    t, d, u, i = escape(title), escape(desc), escape(target), escape(image)

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="utf-8">
  <title>{t}</title>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
  <meta property="og:title" content="{t}">
  <meta property="og:description" content="{d}">
  <meta property="og:image" content="{i}">
  <meta property="og:url" content="{u}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{t}">
  <meta name="twitter:description" content="{d}">
  <meta name="twitter:image" content="{i}">
  <meta name="robots" content="noindex">
  <meta http-equiv="refresh" content="0;url={u}">
  <script>location.replace({target!r});</script>
</head>
<body>
  <p><a href="{u}">कृषि बाज़ार पर देखें →</a></p>
</body>
</html>""")


@router.get("/share/mandi", response_class=HTMLResponse)
def share_mandi(state: str = "", commodity: str = "", district: str = ""):
    # Falls back to the generic hub; upgraded below to the exact crop/state/
    # district page once the price lookup resolves the real DB commodity name
    # (the humans-get-bounced-here target used to be mandi.html?state=...,
    # but that JS-only page is retired — mandi data lives only on /bhav now).
    target = f"{SITE}/bhav"

    # Hindi crop name + rounded rupee, so the WhatsApp preview reads "चावल: ₹4,819"
    # rather than "Rice: ₹6434.67". Imported lazily: bhav.py imports FROM this module
    # at load time, so a top-level import back into it would be circular.
    from backend.routes.bhav import _hindi_name, _rupee, _slugify

    hi_commodity = _hindi_name(commodity) if commodity else "मंडी भाव"
    title = f"{hi_commodity} — आज का मंडी भाव | कृषि मित्र"
    desc = "ताजा मंडी भाव, रुझान और सरकारी दरें — कृषि मित्र, किसान का डिजिटल साथी"

    try:
        data = get_mandi_prices(commodity, district, state)
        prices = (data or {}).get("prices") or []
        if prices:
            p = prices[0]
            cs, ss, ds = (_slugify(p.get("commodity", commodity)),
                          _slugify(p.get("state", state)),
                          _slugify(p.get("district", district)))
            if cs and ss and ds:
                target = f"{SITE}/bhav/{cs}/{ss}/{ds}"
            modal = p.get("modal_price")
            if modal and modal != "-":
                title = f"{_hindi_name(p.get('commodity', commodity))}: {_rupee(modal)}/क्विंटल"
                try:
                    pct = float(p.get("change_pct"))
                    if pct:
                        arrow = "▲" if pct > 0 else "▼"
                        sign = "+" if pct > 0 else ""
                        title += f" ({arrow} {sign}{pct:g}% कल से)"
                except (TypeError, ValueError):
                    pass
                desc = (
                    f"🏪 {p.get('market', '-')} · 📍 {p.get('district', '-')} · "
                    f"📅 {p.get('date', '-')} — ताजा भाव कृषि मित्र पर देखें"
                )
    except Exception:
        pass  # preview falls back to the generic title/description

    # 960px → WhatsApp renders the large preview card (≥300px each side);
    # at the default 330px it falls back to the small square thumbnail.
    image = _crop_image(commodity, 960)
    t, d, u, i = escape(title), escape(desc), escape(target), escape(image)

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="utf-8">
  <title>{t}</title>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="कृषि मित्र (KrashiMitra)">
  <meta property="og:title" content="{t}">
  <meta property="og:description" content="{d}">
  <meta property="og:image" content="{i}">
  <meta property="og:url" content="{u}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{t}">
  <meta name="twitter:description" content="{d}">
  <meta name="twitter:image" content="{i}">
  <meta name="robots" content="noindex">
  <meta http-equiv="refresh" content="0;url={u}">
  <script>location.replace({target!r});</script>
</head>
<body>
  <p><a href="{u}">ताजा मंडी भाव देखें →</a></p>
</body>
</html>""")
