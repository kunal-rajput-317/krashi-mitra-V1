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
    "masoor-me-khad-kab-kitni": "Disc Harrow Seed Drill.jpg",

    # ── trees & agroforestry ──────────────────────────────────────────────
    "sagaun-teak-ki-kheti": "Forest plantation of Tectona grandis in Costa Rica (2017).jpg",
    "poplar-ki-kheti": "Above Ehrenbach, poplar between field and forest.jpg",
    "eucalyptus-safeda-ki-kheti": "NH 72 Highway Dehradun Eucalyptus lined Road India.jpg",
    "chandan-ki-kheti": "Chandanam (Malayalam ചന്ദനം) (30743804600).jpg",
    "mahogany-ki-kheti": "Swietenia mahagoni (1126845222).jpg",
    "bans-ki-kheti": "2255 bamboo - Alain Van den Hende 17072255 licence CC40.jpg",
    "sahjan-munga-ki-kheti": "Cultivos de moringa en el Vivero Forestal de Chimbote 02.jpg",
    "malabar-neem-melia-dubia": "Melia dubia at Periya (1).jpg",

    # ── crops & practices ─────────────────────────────────────────────────
    "kapas-ki-kheti-guide": "Woman picking cotton in Raichur, Karnataka.jpg",
    "parali-prabandhan": "Burning of rice residues after harvest (9190).jpg",
    "dhan-seedhi-buvai-dsr": "A Farmer Cultivating In Punjab.jpg",
    "prakritik-kheti-jeevamrit": '"a Compost pit".jpg',
    "kisan-pehchan-patra-agristack": "Aerial view of agricultural fields in Punjab, India.jpg",
    "kharpatwarnashi-guide": "Cyperus rotundus by kadavoor.JPG",

    # ── Maharashtra series (10 articles, Aug 2026) ────────────────────────
    # Five are state schemes, where Commons has no photograph of the scheme
    # itself — so each takes a Maharashtra farm scene the caption describes
    # honestly, the same way kisan-credit-card takes a photograph of banknotes.
    "namo-shetkari-mahasanman-nidhi": "Along Dhule - Sholapur Road (50755081057).jpg",
    "e-pik-pahani-nondani": "Tomato farming at Gondegaon.jpg",
    "mahadbt-shetkari-yojana": "Baramati, Maharashtra, India. 20 agriculture equipment.jpg",
    "magel-tyala-saur-krushi-pump": "Solar panels in India.jpg",
    "kanda-chal-anudan-yojana": "Baramati, Maharashtra, India. 17 onions.jpg",
    "nagpuri-santra-falgal": "Nagpur orange article.JPG",
    "rabi-jowar-shalu-lagvad": "Sorghum crop Chinawal 04.jpg",
    "haldi-lagvad-sangli": "Turmeric field.jpg",
    "dalimb-telya-rog": "Pomegranate in India 01.jpg",
    "drakhsh-downy-mildew": "Grapes. Nasik.jpg",

    # ── PENDING: curated and licence-checked, article not written yet ──────
    # These ten were verified against Commons (exists, landscape, >=900px, not
    # NonCommercial) but their articles were not written, so the image files
    # were deleted rather than left unreferenced in the repo and listed on
    # /articles/credits. The curation is the expensive part and it is kept here:
    # to resume, write the content module and run
    #     python tools/fetch_article_images.py <slug>
    "moong-ki-kheti": "Green Gram field.jpg",
    "urad-ki-kheti": "Black gram field, Maravanthe.jpg",
    "til-ki-kheti": "Hidaka Kinchakuda Sesame Field 1.JPG",
    "shree-anna-motanaj-millets": "Eleusine coracana (L.) Gaertn.jpg",
    "kisan-drone-chhidkav": "DJI Agras T50 demonstrating sprayers in flight.jpg",
    "dhan-nursery-ropai": "Rice Transplanter in India.jpg",
    "makka-ethanol-maang": "2014-09 Nowaki (17) Zbiór kukurydzy.jpg",
    "dairy-farming-doodh-utpadan": "Sahiwal cows at the dairy unit attached to Bhai Ram Singh Memorial (Gurudwara) Bhaini Sahib, Ludhyana ,Punjab, India.JPG",
    "pashu-thanaila-mastitis": "India - Woman dairy entrepreneur (3975844335).jpg",
    "hara-chara-napier-berseem": "Fodder for Buffaloes.jpeg",

    # ── तमिलनाडु cluster ───────────────────────────────────────────────────
    "tamil-nadu-krishi-guide": "Paddy cultivation Kolli hills JEG3087.jpg",
    "samba-dhan-tamil-nadu": "Paddy Fields Thanjavur.jpg",
    "nariyal-kheti-tamil-nadu": "Lush Green Pollachi.jpg",
    "haldi-kheti-erode-tamil-nadu": "Turmeric field visit.jpg",
    "tapioca-maravalli-tamil-nadu": "Manihot esculenta Cassava plantation in Kalvarayan hills JEG3597.jpg",
    "ragi-kheti-tamil-nadu": "Finger Millet Field at Peddamunagalachedu Village.jpg",
    "moongfali-tikka-rog-tamil-nadu": "Cultivation of peanut crop in Junagadh region of Western India.jpg",
    "madurai-malli-jasmine-kheti": "HiH - Enterprise - 53 - Jasmine Cultivation (3063468166).jpg",
    "tamil-nadu-uttar-poorvi-mansoon": "India - Chennai - Monsoon - 01 (3058208937).jpg",
    "uzhavar-sandhai-tamil-nadu": "Sandhai.jpg",
    "kela-kheti-tamil-nadu": "Banana Fields near Kallanai.jpg",
    "mundu-mirch-ramnad-tamil-nadu": "India - Colours of India - Pepper cultivation (2492156360).jpg",
    "dhan-ke-baad-urad-tamil-nadu": "Black gram field, Maravanthe.jpg",

    # ── ಕರ್ನಾಟಕ cluster ────────────────────────────────────────────────────
    # Karnataka subjects wherever Commons has one: Coorg for coffee, a Raichur
    # sowing for the registry article. Ragi deliberately does NOT reuse
    # "Finger Millet Field at Peddamunagalachedu Village.jpg" — that is already
    # the hero of ragi-kheti-tamil-nadu, and one photograph fronting two
    # articles reads as the same page twice.
    "ragi-guide-karnataka": "View of Ragi crop from the peek of the village.jpg",
    "arecanut-guide-karnataka": "Arecanut plantations.JPG",
    "coffee-guide-karnataka": "Road Coffee Estate Inakanahalli Coorg Jun24 A7CR 01542.jpg",
    "maize-guide-karnataka": "Maize crop in rural India.jpg",
    "tur-guide-karnataka": "New farm technology and extension support leads to bumper crop production. Photo shows a farmer's arhar (pigeonpea) field at village Guma.jpg",
    "sericulture-guide-karnataka": "Silkworm cocoons.jpg",
    "coconut-guide-karnataka": "Coconut Plantation2.jpg",
    "fruits-id-karnataka": "Women Farmers Sowing in Karnataka, India.jpg",
    "raitha-siri-karnataka": "Kaun rice (01).jpg",
    "krishi-bhagya-karnataka": "Farm pond.jpg",

    # ── मध्य प्रदेश cluster ────────────────────────────────────────────────
    # MP subject matter wherever Commons has it: a Harda chickpea field, a
    # Raisen wheat field, a Hoshangabad moong field. Where it does not (garlic,
    # coriander seed, kodo, linseed), the nearest Indian photograph of the crop
    # itself, and the caption says what it actually shows.
    #
    # None of these reuses a file another article already fronts:
    # "Garlic.jpg" belongs to garlic-farming-guide, "Champ de soja.jpg" to
    # soyabean-MP-guide, and the "ggia version" Raisen crop to
    # gehuu-price-analytic-up — one photograph on two pages reads as the same
    # page served twice.
    "soyabean-illi-chakra-bhring-mp": "Soyabean field.jpg",
    "chana-fali-chhedak-illi": "Chickpea field Visit in Harda.jpg",
    "sharbati-gehun-mp": "Wheat field, Raisen district, Madhya Pradesh, India.jpg",
    "dhaniya-ki-kheti-mp": "Coriander Seeds.jpg",
    "lahsun-thrips-baingani-dhabba": "Garlic in Salem.jpg",
    "kodo-kutki-ki-kheti-mp": "Paspalum scrobiculatum (4987845638).jpg",
    "alsi-ki-kheti-mp": "Linum usitatissimum-1-xavier cottage-yercaud-salem-India.jpg",
    "mp-mukhyamantri-kisan-kalyan-yojana":
        "Moong crop in a field in Hoshangabad, Madhya Pradesh, on May 28, 2013.jpg",
    "mp-e-uparjan-panjiyan": "Grain Market, Bhawanigarh.jpg",
    "mp-rbc-6-4-fasal-muavza":
        "Flood waters flooding the fields in Fatehabad District, Haryana, India, 2023.jpg",

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
    "murgi-ranikhet-rog": "Poultry Farm in Namakkal, Tamil Nadu.jpg",
    "machhli-palan-guide": "Aeration systems in an Aqua pond near Eluru.jpg",
    "madhumakhi-palan-guide": "Apiary in the valley.jpg",
    "pashu-lumpy-skin-rog": "Rural women and cattle on a village road in Raichur.jpg",

    # State पशुपालन spokes (2026-09-14). Each is the animal the state is
    # actually known for, photographed in India — the caption says what the
    # frame shows and never claims the state, because only the Hajipur fish
    # market below is documented as being in the state its article is about.
    "bhains-palan-up": "Milking the Buffalo (35403227412).jpg",
    "bakri-palan-rajasthan": "Boy and goats in Rajasthan.jpg",
    "machhli-palan-bihar": "Mallah men selling fishes.jpg",
    # The other two of the five were curated and fetched, then the articles
    # were stopped before they were written — so they follow the PENDING rule
    # above: the curation stays here, the files do not sit in the repo
    # attributing pictures nothing displays. To resume, write the content
    # module (Tamil for Namakkal layer poultry, Kannada for KMF/Nandini dairy)
    # and run: python tools/fetch_article_images.py <slug>
    "murgi-palan-tamil-nadu": "Feeding the Chickens (35412883672).jpg",
    "dairy-guide-karnataka": "Coming for Milking... (22296679258).jpg",

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

    # ── यूरिया cluster (Aug 2026) ─────────────────────────────────────────
    # No free photograph exists of neem oil being sprayed onto urea prills, so
    # the neem article uses the raw material the coating is made from and the
    # caption says exactly that.
    "neem-coated-urea-guide": "Collected fruits and seeds of (Azadirachta indica) Neem tree in Visakhapatnam.jpg",
    "urea-ke-baad-pani-kab": "Agricultural irrigation pump set with borewell, Vrindavan, Uttar Pradesh, India.jpg",

    # ── यूरिया cluster round 2 (Sep 2026) ─────────────────────────────────
    # Each of the three is the literal subject: a farmer broadcasting
    # fertiliser by hand for the per-acre dose article, a UP paddy field for
    # the धान schedule, and a UP field for the फायदे-नुकसान piece — where the
    # damage being described (excess N) leaves no photographable signature, so
    # the caption says it is a field and does not claim to show the harm.
    "ek-acre-bigha-kitna-urea": "An Indian farmer spreading fertilizer over a crop.jpg",
    "dhan-me-urea-kab-kitna": "Rice fields Uttar Pradesh (1).jpg",
    "urea-ke-fayde-aur-nuksan": "Farmland in Allahabad,India.jpg",

    # ── रबी round (Sep 2026) ──────────────────────────────────────────────
    # The wheat piece is about the fertiliser that goes in at sowing, so its
    # picture is a field being prepared for wheat, not a ripe crop. Late blight
    # is one of the few diseases Commons has a real, correctly-identified
    # photograph of, so that article shows the actual pathogen.
    "gehun-me-khad-kab-kitni": "Agriculture in India tractor farming Punjab preparing field for a wheat crop without burning previous crop stalk.jpg",
    "sarson-ki-unnat-kheti": "Mustard field.jpg",
    "aloo-pachheti-jhulsa": "Phytophthora infestans on potato leaf.jpg",

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
    "tomato-guide-karnataka": "20160831Solanum lycopersicum4.jpg",
    "tomato-leaf-curl": "20160810Solanum lycopersicum1.jpg",
    "up-agriculture-guide": "A view of landscape pre with harvest wheat crop in Punjab.jpg",
    "gehuu-price-analytic-up": "Woman harvesting wheat, Raisen district, Madhya Pradesh, India ggia version.jpg",
    # These two had their own art, but it was unusable: frontend/images/
    # articles/potato.webp carries the same baked-in transparency checkerboard,
    # and the yojana/pmkisan art was a mock Government of India cheque made
    # out to a named person — not something to serve as a hero or an og:image.
    # (That file, and the other unusable yojana exports, have since been
    # deleted; this note stays so the picks are not revisited.)
    "potato_guide_up": "Aardappelveld bij Heusden.jpg",
    "PM-kisan-samman-nidhi": "1. Mera Gaon Mera Gaurav yojna of GOI implemented in villages by IARI New Delhi.jpg",
    # ── मुंबई / वाशी APMC cluster ─────────────────────────────────────────
    # Selling into the Mumbai wholesale market. Indian subject matter
    # throughout; where no photograph of the Vashi yards themselves is free,
    # another Indian wholesale market stands in and the caption says so.
    "vashi-apmc-mandi-guide": "Vegetable market in Mumbai.jpg",
    "mumbai-mandi-adat-kanoon": "Buying groceries in Mumbai (1109).jpg",
    "mumbai-mandi-kharcha-hisab": "Mumbai vegetables.JPG",
    "apmc-adatiya-license-guide": "Colourful vegetables Mumbai market.jpg",
    "apmc-bahar-seedhi-bikri": "Sri ganesh wholesale vegetables in rajahmundry night.jpg",
    "pyaj-nashik-se-vashi-bhav": "Onion Mandi.jpg",
    "batata-aloo-vashi-mandi": "Potatofarmer.jpg",
    "tamatar-mumbai-mandi-bhav": "Potato Bean Tomato Veg Stall Ooty Market Nilgiris Aug25 A7CR 07103.jpg",
    "bhindi-mirch-vashi-sabji": "India - Koyambedu Market - Market 06 (3986891340).jpg",
    "hapus-aam-mumbai-market": "Ratnagiri Alphonso Tree.jpg",
    "kela-mumbai-mandi-ganesh": "India - Koyambedu Market - Banana 01 (3986186559).jpg",
    "anaaj-dal-vashi-masala": "Spices Mandi.jpg",
    "mumbai-mandi-transport-vahan": "Unloading onion.jpg",
    "sabji-packing-grading-mumbai": "India - Koyambedu Market - Market 03 (3987093932).jpg",
    "mumbai-mandi-payment-suraksha": "India - Koyambedu Market - Market 08 (3986141067).jpg",

    # ── रबी batch, सितंबर 2026 (12 articles) ──────────────────────────────
    # Three of the twelve already had a hero on disk from an earlier batch
    # (chana-fali-chhedak-illi, hara-chara-napier-berseem,
    # pashu-thanaila-mastitis) and keep the entries above.
    #
    # Two are deliberately not photographs of the thing the article treats,
    # because no free one exists: the सफेद रतुआ page takes a healthy mustard
    # crop and the पाला page takes a foggy winter morning over a mustard field.
    # Both captions say so — neither claims the reader is looking at the damage.
    "gehun-deemak-niyantran": "Odontotermes obesus Termites Isoptera (1) 22.jpg",
    "sarso-safed-ratua": "Mustard plant flowers in India (2016).jpg",
    "nilgai-awara-pashu-fasal-bachav": "Nilgai, Lakeshwari, Gwalior district, India.jpg",
    "pala-tushar-se-fasal-bachav": "A winter morning in my village (25733868476).jpg",
    "gehun-me-sinchai-kab": "Agricultural irrigation pump set with borewell, Vrindavan, Uttar Pradesh, India 02.jpg",
    "jau-ki-kheti": "Fields of barley (29040669486).jpg",
    "tarbandi-yojana-subsidy": "Paddy field and barbed wire fence in Bundelkhand.jpg",
    "pm-dhan-dhaanya-krishi-yojana": "Apna Khet Village Malasar Farm View.jpg",
    "dhan-nami-mandi-rejection": "Farmer manually harvesting rice in Raichur, Karnataka.jpg",

    # ── सितंबर 2026, दूसरा बैच ────────────────────────────────────────────
    # The गन्ना file is categorised on Commons under "Fields in Uttar Pradesh",
    # which is the state the शरदकालीन article is written for. The मक्का one is
    # an actual winter maize crop (Udaipur, Rajasthan) — the caption says where.
    # The FMD page takes healthy village cattle: no free photograph of the
    # mouth or hoof lesions exists that we may use commercially, and the caption
    # never implies the reader is looking at the disease.
    "sharadkalin-ganna-buvai": "Sugarcane Agriculture.jpg",
    # No free photograph of a पर्ची or a mill weighbridge exists on Commons,
    # so the सट्टा/पर्ची article uses the moment the पर्ची actually governs —
    # the harvest — and its caption says so. A harvest scene also keeps it
    # visually distinct from the three cane articles that use field shots.
    # (The better-framed Doddagowdana harvest shot is CC BY-SA 4.0 but its
    # author asks to be contacted before commercial use, and this site
    # carries AdSense — so it is not used.)
    "ganna-satta-parchi-up":
        "File.sugacane crop.jpg",
    "rabi-makka-ki-kheti": "A winter crop of maize near Sei dam in Kotra tehsil, Udaipur district, Rajasthan, in May 2019.jpg",
    "pashu-khurpaka-muhpaka-fmd": "Dairy Project at Kasturbagram Rural Institute, Indore.jpg",

    # गलघोंटू hits buffalo hardest, so the hero is an Indian buffalo breed on a
    # farm. No usable free photograph of the swollen throat exists — the caption
    # says the animals shown are healthy.
    "pashu-galghotu-rog": "Jafarabadi buffalo in village.jpg",

    # ── सितंबर 2026, तीसरा बैच ─────────────────────────────────────────────
    # The धान खरीद article is written for Uttar Pradesh, and this is a paddy
    # field photographed in Uttar Pradesh. No free photograph of a UP क्रय
    # केंद्र (procurement centre) exists on Commons that we may use
    # commercially, so the crop stands in and the caption says exactly that.
    # Frame (2) of the series, not (1): dhan-me-urea-kab-kitna already holds (1)
    # and two articles sharing one photograph look like a broken card grid.
    "up-dhan-kharid-panjikaran": "Rice fields Uttar Pradesh (2).jpg",

    # ── सितंबर 2026, चौथा बैच ──────────────────────────────────────────────
    # The rodent article gets the actual pest: Bandicota bengalensis, the lesser
    # bandicoot rat, which AICRP names the predominant rodent of Indian
    # irrigated agriculture. Photographed in India (Mike Prince, Bangalore),
    # CC BY 2.0 — so it is the real organism and not a stand-in crop.
    "khet-me-chuha-niyantran": "Lesser Bandicoot-Rat.jpg",

    # ऊसर/क्षारीय भूमि सुधार. Commons has no usable photograph of Indian sodic
    # land — every "salt affected soil" hit is a foreign salt pan or a portrait
    # crop. So the hero is the practice the article says cannot be skipped:
    # green manuring in an Indian farmer's field (Manav Vikas Sansthan,
    # CC BY-SA 4.0, 5120×2880). The caption says it shows green manure, not
    # usar land.
    "usar-bhumi-sudhar-jipsam": "Green Manuring by Manav Vikas Sansthan.jpg",
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

    # The straight-fertiliser guides — same product art as the shop, so the
    # article and the product page a farmer lands on next show the same bag.
    "ssp-khad-guide": "images/fertilizers/SSP.webp",
    "npk-complex-khad-guide": "images/fertilizers/NPK.webp",
    "zinc-ki-kami-fasal": "images/fertilizers/zinc_sulphate.jpg",
    "sulphur-gandhak-ki-kami": "images/fertilizers/ammonium-sulphate.webp",

    # The यूरिया cluster's three remaining heroes. The rate article is about the
    # bag itself, the spray article about the pump the solution goes into, and
    # the comparison article about the other nitrogen bag on the shelf — each
    # picture is the actual subject, so they come from art already in the repo.
    "urea-bori-rate-subsidy": "images/fertilizers/Urea.webp",
    "urea-chhidkav-ghol-matra": "images/tools/battery-sprayer-12V.webp",
    "urea-ammonium-sulphate-can-tulna": "images/fertilizers/ammonium-sulphate.webp",

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
