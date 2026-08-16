# ============================================================
# KrashiMitra — article hero image sources
#
# name → Wikimedia Commons filename. `tools/fetch_article_images.py` turns each
# into frontend/images/articles/<name>.webp and records the licence + author in
# frontend/images/articles/CREDITS.json.
#
# Rules for adding one:
#   • landscape and >= 1200px wide — the figure renders at 1200×675
#   • prefer Indian subject matter; a Maharashtra vineyard beats a Californian
#     one on an article about Nashik grapes
#   • prefer the actual subject. Where no free photograph of the specific
#     pathogen exists (bacterial leaf blight, leaf curl virus), we use the crop
#     and the caption says so — it never claims to show the disease.
#   • run `python tools/fetch_article_images.py --verify` after editing: Commons
#     renames and deletes files, and six of our old hotlinks had already rotted.
#
# Articles served by an image already in the repo (images/yojana/*, seeds/*,
# fertilizers/*, plants/*) are not listed here — they point straight at it.
# ============================================================

import re


def body_name(original: str) -> str:
    """Local basename for an in-body illustration, from its old hotlink name.

    "Bright red tomato and cross section02.jpg" → "body-bright-red-tomato-and-
    cross-section02". Derived rather than hand-assigned so the mapping between
    the URL in the HTML and the file on disk cannot drift.
    """
    stem = original.rsplit(".", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return f"body-{slug}"


IMAGES = {
    # ── crops & cultivation ────────────────────────────────────────────────
    "adrak-haldi-kand-sadan": "Ginger rhizome.jpg",
    "arhar-tur-kheti-guide": "Cajanus cajan Steve Hurst 1.jpg",
    "baingan-tana-phal-chhedak": "Solanum melongena 03458.JPG",
    "bajra-jogiya-rog-rajasthan": "Pearl millet - Pennisetum glaucum.jpg",
    "bhindi-pila-mozek": "Senegal Okra field.jpg",
    "chana-ki-kheti": "CSIRO ScienceImage 3600 Chickpeas in glasshouse.jpg",
    "chana-unnat-kheti": "Cicer arietinum noir MHNT.BOT.2017.12.2.jpg",
    "gehun-unnat-kheti": "Harduaganj wheat field.jpg",
    "kela-panama-wilt": "Musa acuminata - banana trees (Watling's Well Banana Hole, San Salvador Island, Bahamas) 2 (15805691884).jpg",
    "masoor-ki-kheti": "Lens culinaris flowers.jpg",
    "matar-ki-kheti": "Pisum sativum MHNT.BOT.2010.12.9.jpg",
    "mushroom-ki-kheti": "Био ферма Балерина - ферма за култивирана гъба Кладница.jpg",
    "paat-jute-sadai-kolkata": "A jute farmer in the flooded fields of West Bengal.jpg",
    "ganna-choti-bedhak": "Sugar cane farming in Rajasthan.jpg",
    "gobhi-diamondback-moth": "Starr-091023-8506-Brassica oleracea var capitata-field of crops-Kula-Maui (24691249010).jpg",
    "kapas-gulabi-sundi": "பருத்தி1.jpg",
    "dhan-bhura-fudka-up": "FARMERS ENGAGED IN RICE CULTIVATION, KUTTANAD.jpg",
    "dhan-jivanu-jhulsa-blb": "Apatani Rice Paddies.jpg",

    # ── trees & agroforestry ──────────────────────────────────────────────
    "sagaun-teak-ki-kheti": "Forest plantation of Tectona grandis in Costa Rica (2017).jpg",
    "poplar-ki-kheti": "Above Ehrenbach, poplar between field and forest.jpg",
    "eucalyptus-safeda-ki-kheti": "NH 72 Highway Dehradun Eucalyptus lined Road India.jpg",
    "chandan-ki-kheti": "Chandanam (Malayalam ചന്ദനം) (30743804600).jpg",
    "mahogany-ki-kheti": "Swietenia mahagoni (1126845222).jpg",
    "bans-ki-kheti": "2255 bamboo - Alain Van den Hende 17072255 licence CC40.jpg",
    "sahjan-munga-ki-kheti": "Cultivos de moringa en el Vivero Forestal de Chimbote 02.jpg",
    "malabar-neem-melia-dubia": "Melia dubia at Periya (1).jpg",

    # ── pests & diseases (the actual organism, where one exists free) ──────
    "dhan-tana-chhedak": "Rice yellow stem borer.jpg",
    "makka-fall-armyworm": "Lagarta do Cartucho 01.jpg",
    "sarso-mahu-chepa": "Lipaphis erysimi 2.jpg",
    "gehun-gulli-danda": "Phalaris minor in Jalalpur, Patiala district 01.jpg",
    "gehun-ratua-rog": "Puccinia triticina (04).jpg",
    "aalu-pichheti-jhulsa": "Phytophthora infestans on potato leaf.jpg",
    "dhan-jhonka-rog": "LPCC-748-Arrossar amb piriculariosi.jpg",

    # ── livestock & allied ────────────────────────────────────────────────
    "bakri-palan-guide": "Goat rearing rural woman India village livestock management.jpg",
    "murgi-palan-guide": "Broiler Chickens 001.jpg",
    "murgi-palan-backyard": "Free range chicken flock.jpg",
    "machhli-palan-guide": "Aeration systems in an Aqua pond near Eluru.jpg",
    "madhumakhi-palan-guide": "Apiary in the valley.jpg",
    "pashu-lumpy-skin-rog": "Rural women and cattle on a village road in Raichur.jpg",

    # ── schemes, markets, inputs ──────────────────────────────────────────
    "bhandaran-ghun-keet": "Traditional granary and preservation of grains.jpg",
    "enam-online-fasal-bechna": "Vegetable market, Ahmedabad.jpg",
    "fpo-kisan-utpadak-sangathan": "The Union Minister for Agriculture, Shri Radha Mohan Singh at the ‘National conference on Strengthening of Cooperative - Education and Training system’, in New Delhi on January 20, 2015.jpg",
    "krishi-yantra-subsidy": "India Uttar Pradesh tractor.jpg",
    "mitti-jaanch-soil-health-card": "Soil Scientist Nathan Haile examines soil condition in soil samples taken in the pasture. (24821293820).jpg",
    "pm-kusum-solar-pump-yojana": "SOLAR POWER IRRIGATION RICE FARMING.jpg",
    "jalbharav-baadh-fasal-bachav": "Flooded paddy field Raichur Karnataka India monsoon irrigation July 2025.jpg",
    # frontend/images/yojana/{kcc,pmfby,sinchai} were the obvious picks for
    # these three, but all three were exported with the editor's transparency
    # checkerboard baked in as real pixels. It lifts off the flat background but
    # not out of the drop shadows and glows, so they are not usable as heroes.
    "kisan-credit-card": "INR.JPG",
    "pm-fasal-bima-yojana-2026": "Verse champ de blé01.jpg",
    "pmksy-drip-sinchai-subsidy": "Driprication.jpg",

    # ── replacing the Commons hotlinks the legacy articles used ───────────
    "aam-utpadan-up": "Anish nellickal 25 .jpg",
    "aam-utpadan-mp": "Anish nellickal 27 .jpg",
    "anaar-maharastra": "Pomegranate fruit - whole and piece with arils.jpg",
    "apple-kashmir": "Red Apple.jpg",
    "chini-utpadan": "Sugar 2xmacro.jpg",
    "garlic-farming-guide": "Garlic.jpg",
    "grapes-maharastra": "Sula Grape Vineyard.jpg",
    "karnataka-monsoon": "Monsoon Clouds 6260.JPG",
    "land-price-up": "Agricultural irrigation pump set with borewell, Vrindavan, Uttar Pradesh, India.jpg",
    "litchi-guide-bihar": "Litchi chinensis Luc Viatour.jpg",
    "mausam-guide": "Monsoon clouds in Bengal India.jpg",
    "moongfali-guide-rajisthan": "Arachis hypogaea 004.JPG",
    "online-farming-guide": "Onion field.jpg",
    "paddy-guide-karnataka": "Paddy nursery in Raichur, Karnataka.jpg",
    "sarso-guide-up": "Mustard flower in Assam.jpg",
    "soyabean-MP-guide": "Champ de soja.jpg",
    "tomato-guide-up": "20160831Solanum lycopersicum4.jpg",
    "tomato-leaf-curl": "20160810Solanum lycopersicum1.jpg",
    "up-agriculture-guide": "A view of landscape pre with harvest wheat crop in Punjab.jpg",
    "gehuu-price-analytic-up": "Woman harvesting wheat, Raisen district, Madhya Pradesh, India ggia version.jpg",
    # These two had their own art, but it was unusable: frontend/images/
    # articles/potato.webp carries the same baked-in transparency checkerboard,
    # and images/yojana/pmkisan.png is a mock Government of India cheque made
    # out to a named person — not something to serve as a hero or an og:image.
    "potato_guide_up": "Aardappelveld bij Heusden.jpg",
    "PM-kisan-samman-nidhi": "1. Mera Gaon Mera Gaurav yojna of GOI implemented in villages by IARI New Delhi.jpg",
}


# In-body illustrations on the hand-written articles.
#
# Those pages carry a second and third photograph inside the text, also
# hotlinked from Commons. They are self-hosted the same way, one local file per
# original so a page that showed five different pictures still shows five.
#
#   "<filename as it appears in the old hotlink>": "<Commons file to fetch>"
#
# Six entries differ on the two sides: those originals were renamed or deleted
# upstream and had been rendering as broken-image icons on live pages. The key
# is kept as-is so the rewrite still finds them in the HTML.
BODY = {
    "Bright red tomato and cross section02.jpg": "20160820Solanum lycopersicum1.jpg",
    "Cumulus clouds panorama.jpg": "Monsoon clouds in Bengal India.jpg",
    "Garlic.jpg": "Garlic.jpg",
    "Hapus Mango.jpg": "Anish nellickal 20.jpg",
    "Litchi chinensis Luc Viatour.jpg": "Litchi chinensis Luc Viatour.jpg",
    "Mango 4.jpg": "Anish nellickal 29 .jpg",
    "Onion on White.JPG": "Onion on White.JPG",
    "Onion_field.jpg": "Onion field.jpg",
    "Paddy field.jpg": "Paddy field.jpg",
    "Pomegranate fruit - whole and piece with arils.jpg": "Pomegranate fruit - whole and piece with arils.jpg",
    "Red_Apple.jpg": "Red Apple.jpg",
    "Soybean.USDA.jpg": "Closeup of High Oleic Soybeans (10873119213).jpg",
    "Sugar 2xmacro.jpg": "Sugar 2xmacro.jpg",
    "Sugarcane.jpg": "Harvesting Sugarcane Doddagowdana Koppalu Aug24 A7CR 02231.jpg",
    "Tomato_plant.jpg": "Tomato plant.jpg",
    "Wheat close-up.JPG": "Wheat close-up.JPG",
    # ── dead upstream, substituted ──
    # A value starting with "images/" is a file already in this repo. Commons
    # has no usable photograph of applied fertiliser — the category is urea
    # crystals under a microscope — so this one comes from our own shop art.
    "Chemical_fertilizers.jpg": "images/fertilizers/NPK.webp",
    "Grain_market_in_Punjab.jpg": "Agricultural land of northern india.jpg",
    "Onion_harvesting.jpg": "Onion harvest.jpg",
    "Solar_powered_water_pump.jpg": "SOLAR POWER IRRIGATION RICE FARMING.jpg",
    "Table_grapes_on_vine.jpg": "Grape Garden.JPG",
    "Tomaten_am_Strauch.jpg": "20180518Solanum lycopersicum1.jpg",
}


# Images already in the repo that were sitting unused (or used only by the shop)
# while the matching article showed an emoji. They go through the same pipeline
# so every hero on the site is one size and one format.
#
# These are annotated diagrams and product art, not photographs — cropping them
# to 16:9 would cut the Hindi labels off, so they are letterboxed onto a
# background sampled from their own edges instead.
LOCAL = {
    "beej-upchar-vidhi": "images/seeds/wheat-seed-HD-2967.webp",
    "pyaj-kharif-kheti-bhandaran": "images/seeds/onion-seed-nasik-red.webp",
    "soyabean-pila-mozek-mp": "images/seeds/soyabean-js-335.webp",
    "mirch-kala-thrips": "images/plants/chilli-rog-weak-leaf.webp",
    "nano-urea-nano-dap": "images/fertilizers/Urea.webp",
    "keet-niyantran": "images/Pesticides/neem-oil.webp",

    # Hand-written articles that already showed their own picture but still
    # declared the site banner as og:image, and whose card loaded the full-size
    # file. Normalising them here gives them the same 1200×675 hero and 480px
    # card cut as everything else.
    "chilli-guide-karnataka": "images/plants/black-chilli-karnataka.webp",
    "DAP-guide-up": "images/fertilizers/DAP.webp",
    "MOP-guide": "images/fertilizers/MOP.webp",
    "urea-guide-up": "images/diseases/urea-full-guide.webp",
    "jaivik-khad": "images/fertilizers/vermicompost.webp",
    "makka-guide-up": "images/seeds/makka-hybrid-crop.webp",
    "ganna-guide-up": "images/diseases/ganne-ke-khet-up.webp",
    "ganna-pricing-analytics-up": "images/Ganna/ganna-SAP.webp",
    "ganna-rog": "images/diseases/sugarcane-red-rot-shown-img.webp",
    "motha-ghaas-UP": "images/articles/motha-ghaas-01.webp",
}
