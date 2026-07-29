# One-time generator for the /map static assets, per state:
#   frontend/data/<slug>-districts.geojson          (minified, self-hosted boundaries)
#   frontend/images/<prefix>-district-map.png       (full labeled map, page + download)
#   frontend/images/<prefix>-district-map.webp      (light display copy)
#   frontend/images/<prefix>-og.png                 (1200x630 social/og card)
# Boundaries: udit-001/india-maps-data (Census of India). Needs playwright+chromium.
# Re-run only if district boundaries change or the map design is redone.
#
#   python make_state_maps.py                 # every state below
#   python make_state_maps.py rajasthan       # just one

import base64, json, math, os, sys, tempfile, urllib.request
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_URL = ("https://raw.githubusercontent.com/udit-001/india-maps-data/"
           "main/geojson/states/{source}.geojson")
OUT_DIR = ROOT / "frontend" / "data"
IMG_DIR = ROOT / "frontend" / "images"
LOGO    = ROOT / "frontend" / "assets" / "krashimitra_logo.png"

UP_HINDI = {
 "Agra":"आगरा","Aligarh":"अलीगढ़","Ambedkar Nagar":"अंबेडकर नगर","Amethi":"अमेठी",
 "Amroha":"अमरोहा","Auraiya":"औरैया","Ayodhya":"अयोध्या","Azamgarh":"आज़मगढ़",
 "Baghpat":"बागपत","Bahraich":"बहराइच","Ballia":"बलिया","Balrampur":"बलरामपुर",
 "Banda":"बांदा","Barabanki":"बाराबंकी","Bareilly":"बरेली","Basti":"बस्ती",
 "Bhadohi":"भदोही","Bijnor":"बिजनौर","Budaun":"बदायूं","Bulandshahr":"बुलंदशहर",
 "Chandauli":"चंदौली","Chitrakoot":"चित्रकूट","Deoria":"देवरिया","Etah":"एटा",
 "Etawah":"इटावा","Farrukhabad":"फर्रुखाबाद","Fatehpur":"फतेहपुर","Firozabad":"फिरोज़ाबाद",
 "Gautam Buddha Nagar":"गौतम बुद्ध नगर","Ghaziabad":"गाज़ियाबाद","Ghazipur":"गाज़ीपुर",
 "Gonda":"गोंडा","Gorakhpur":"गोरखपुर","Hamirpur":"हमीरपुर","Hapur":"हापुड़",
 "Hardoi":"हरदोई","Hathras":"हाथरस","Jalaun":"जालौन","Jaunpur":"जौनपुर",
 "Jhansi":"झांसी","Kannauj":"कन्नौज","Kanpur Dehat":"कानपुर देहात","Kanpur Nagar":"कानपुर नगर",
 "Kasganj":"कासगंज","Kaushambi":"कौशांबी","Kushinagar":"कुशीनगर","Lakhimpur Kheri":"लखीमपुर खीरी",
 "Lalitpur":"ललितपुर","Lucknow":"लखनऊ","Maharajganj":"महाराजगंज","Mahoba":"महोबा",
 "Mainpuri":"मैनपुरी","Mathura":"मथुरा","Mau":"मऊ","Meerut":"मेरठ",
 "Mirzapur":"मिर्ज़ापुर","Moradabad":"मुरादाबाद","Muzaffarnagar":"मुज़फ्फरनगर","Pilibhit":"पीलीभीत",
 "Pratapgarh":"प्रतापगढ़","Prayagraj":"प्रयागराज","Rae Bareli":"रायबरेली","Rampur":"रामपुर",
 "Saharanpur":"सहारनपुर","Sambhal":"संभल","Sant Kabir Nagar":"संत कबीर नगर","Shahjahanpur":"शाहजहांपुर",
 "Shamli":"शामली","Shrawasti":"श्रावस्ती","Siddharthnagar":"सिद्धार्थनगर","Sitapur":"सीतापुर",
 "Sonbhadra":"सोनभद्र","Sultanpur":"सुल्तानपुर","Unnao":"उन्नाव","Varanasi":"वाराणसी",
}

# Census district set — predates Rajasthan's 2023 reorganisation, so the newer
# Beawar / Deeg / Didwana-Kuchaman etc. are not separate polygons here.
RAJ_HINDI = {
 "Ajmer":"अजमेर","Alwar":"अलवर","Banswara":"बांसवाड़ा","Baran":"बारां",
 "Barmer":"बाड़मेर","Bharatpur":"भरतपुर","Bhilwara":"भीलवाड़ा","Bikaner":"बीकानेर",
 "Bundi":"बूंदी","Chittorgarh":"चित्तौड़गढ़","Churu":"चूरू","Dausa":"दौसा",
 "Dholpur":"धौलपुर","Dungarpur":"डूंगरपुर","Ganganagar":"श्रीगंगानगर","Hanumangarh":"हनुमानगढ़",
 "Jaipur":"जयपुर","Jaisalmer":"जैसलमेर","Jalore":"जालोर","Jhalawar":"झालावाड़",
 "Jhunjhunu":"झुंझुनूं","Jodhpur":"जोधपुर","Karauli":"करौली","Kota":"कोटा",
 "Nagaur":"नागौर","Pali":"पाली","Pratapgarh":"प्रतापगढ़","Rajsamand":"राजसमंद",
 "Sawai Madhopur":"सवाई माधोपुर","Sikar":"सीकर","Sirohi":"सिरोही","Tonk":"टोंक",
 "Udaipur":"उदयपुर",
}

MP_HINDI = {
 "Agar Malwa":"आगर मालवा","Alirajpur":"अलीराजपुर","Anuppur":"अनूपपुर","Ashoknagar":"अशोकनगर",
 "Balaghat":"बालाघाट","Barwani":"बड़वानी","Betul":"बैतूल","Bhind":"भिंड",
 "Bhopal":"भोपाल","Burhanpur":"बुरहानपुर","Chhatarpur":"छतरपुर","Chhindwara":"छिंदवाड़ा",
 "Damoh":"दमोह","Datia":"दतिया","Dewas":"देवास","Dhar":"धार",
 "Dindori":"डिंडोरी","Guna":"गुना","Gwalior":"ग्वालियर","Harda":"हरदा",
 "Hoshangabad":"नर्मदापुरम","Indore":"इंदौर","Jabalpur":"जबलपुर","Jhabua":"झाबुआ",
 "Katni":"कटनी","Khandwa":"खंडवा","Khargone":"खरगोन","Mandla":"मंडला",
 "Mandsaur":"मंदसौर","Morena":"मुरैना","Narsinghpur":"नरसिंहपुर","Neemuch":"नीमच",
 "Niwari":"निवाड़ी","Panna":"पन्ना","Raisen":"रायसेन","Rajgarh":"राजगढ़",
 "Ratlam":"रतलाम","Rewa":"रीवा","Sagar":"सागर","Satna":"सतना",
 "Sehore":"सीहोर","Seoni":"सिवनी","Shahdol":"शहडोल","Shajapur":"शाजापुर",
 "Sheopur":"श्योपुर","Shivpuri":"शिवपुरी","Sidhi":"सीधी","Singrauli":"सिंगरौली",
 "Tikamgarh":"टीकमगढ़","Ujjain":"उज्जैन","Umaria":"उमरिया","Vidisha":"विदिशा",
}

BIHAR_HINDI = {
 "Araria":"अररिया","Arwal":"अरवल","Aurangabad":"औरंगाबाद","Banka":"बांका",
 "Begusarai":"बेगूसराय","Bhagalpur":"भागलपुर","Bhojpur":"भोजपुर","Buxar":"बक्सर",
 "Darbhanga":"दरभंगा","East Champaran":"पूर्वी चंपारण","Gaya":"गया","Gopalganj":"गोपालगंज",
 "Jamui":"जमुई","Jehanabad":"जहानाबाद","Kaimur":"कैमूर","Katihar":"कटिहार",
 "Khagaria":"खगड़िया","Kishanganj":"किशनगंज","Lakhisarai":"लखीसराय","Madhepura":"मधेपुरा",
 "Madhubani":"मधुबनी","Munger":"मुंगेर","Muzaffarpur":"मुजफ्फरपुर","Nalanda":"नालंदा",
 "Nawada":"नवादा","Patna":"पटना","Purnia":"पूर्णिया","Rohtas":"रोहतास",
 "Saharsa":"सहरसा","Samastipur":"समस्तीपुर","Saran":"सारण","Sheikhpura":"शेखपुरा",
 "Sheohar":"शिवहर","Sitamarhi":"सीतामढ़ी","Siwan":"सीवान","Supaul":"सुपौल",
 "Vaishali":"वैशाली","West Champaran":"पश्चिमी चंपारण",
}

MH_HINDI = {
 "Ahmednagar":"अहमदनगर","Akola":"अकोला","Amravati":"अमरावती","Aurangabad":"छत्रपति संभाजीनगर",
 "Beed":"बीड","Bhandara":"भंडारा","Buldhana":"बुलढाणा","Chandrapur":"चंद्रपुर",
 "Dhule":"धुले","Gadchiroli":"गड़चिरोली","Gondia":"गोंदिया","Hingoli":"हिंगोली",
 "Jalgaon":"जलगांव","Jalna":"जालना","Kolhapur":"कोल्हापुर","Latur":"लातूर",
 "Mumbai":"मुंबई","Nagpur":"नागपुर","Nanded":"नांदेड़","Nandurbar":"नंदुरबार",
 "Nashik":"नासिक","Osmanabad":"धाराशिव","Palghar":"पालघर","Parbhani":"परभणी",
 "Pune":"पुणे","Raigad":"रायगढ़","Ratnagiri":"रत्नागिरी","Sangli":"सांगली",
 "Satara":"सातारा","Sindhudurg":"सिंधुदुर्ग","Solapur":"सोलापुर","Thane":"ठाणे",
 "Wardha":"वर्धा","Washim":"वाशिम","Yavatmal":"यवतमाल",
}

PUNJAB_HINDI = {
 "Amritsar":"अमृतसर","Barnala":"बरनाला","Bathinda":"बठिंडा","Faridkot":"फरीदकोट",
 "Fatehgarh Sahib":"फतेहगढ़ साहिब","Fazilka":"फाजिल्का","Ferozepur":"फिरोजपुर","Gurdaspur":"गुरदासपुर",
 "Hoshiarpur":"होशियारपुर","Jalandhar":"जालंधर","Kapurthala":"कपूरथला","Ludhiana":"लुधियाना",
 "Mansa":"मानसा","Moga":"मोगा","Pathankot":"पठानकोट","Patiala":"पटियाला",
 "Rupnagar":"रूपनगर","S.A.S. Nagar":"मोहाली","Sangrur":"संगरूर",
 "Shahid Bhagat Singh Nagar":"नवांशहर","Sri Muktsar Sahib":"मुक्तसर","Tarn Taran":"तरनतारन",
}

HARYANA_HINDI = {
 "Ambala":"अंबाला","Bhiwani":"भिवानी","Charkhi Dadri":"चरखी दादरी","Faridabad":"फरीदाबाद",
 "Fatehabad":"फतेहाबाद","Gurugram":"गुरुग्राम","Hisar":"हिसार","Jhajjar":"झज्जर",
 "Jind":"जींद","Kaithal":"कैथल","Karnal":"करनाल","Kurukshetra":"कुरुक्षेत्र",
 "Mahendragarh":"महेंद्रगढ़","Nuh":"नूंह","Palwal":"पलवल","Panchkula":"पंचकूला",
 "Panipat":"पानीपत","Rewari":"रेवाड़ी","Rohtak":"रोहतक","Sirsa":"सिरसा",
 "Sonipat":"सोनीपत","Yamunanagar":"यमुनानगर",
}

CHHATTISGARH_HINDI = {
 "Bastar":"बस्तर","Bijapur":"बीजापुर","Bilaspur":"बिलासपुर","Dantewada":"दंतेवाड़ा",
 "Dhamtari":"धमतरी","Durg":"दुर्ग","Gariaband":"गरियाबंद","Janjgir - Champa":"जांजगीर-चांपा",
 "Jashpur":"जशपुर","Kanker":"कांकेर","Kawardha":"कबीरधाम (कवर्धा)","Kondagaon":"कोंडागांव",
 "Korba":"कोरबा","Koriya":"कोरिया","Mahasamund":"महासमुंद","Mungeli":"मुंगेली",
 "Narayanpur":"नारायणपुर","Raigarh":"रायगढ़","Raipur":"रायपुर","Rajnandgaon":"राजनांदगांव",
 "Sukma":"सुकमा","Surajpur":"सूरजपुर","Surguja":"सरगुजा",
 "Balod":"बालोद",
 "Baloda Bazar":"बलौदा बाज़ार",
 "Balrampur":"बलरामपुर",
 "Bametara":"बेमेतरा",
 "Dakshin Bastar Dantewada":"दक्षिण बस्तर दंतेवाड़ा",
 "Janjgir Champa":"जांजगीर-चांपा",
 "Kabeerdham":"कबीरधाम",
 "Uttar Bastar Kanker":"उत्तर बस्तर कांकेर"
}

GUJARAT_HINDI = {
 "Ahmedabad":"अहमदाबाद","Amreli":"अमरेली","Anand":"आणंद","Aravalli":"अरवल्ली",
 "Banaskantha":"बनासकांठा","Bharuch":"भरूच","Bhavnagar":"भावनगर","Botad":"बोताद",
 "Chhota Udaipur":"छोटा उदयपुर","Dahod":"दाहोद","Dang":"डांग","Devbhoomi Dwarka":"देवभूमि द्वारका",
 "Gandhinagar":"गांधीनगर","Gir Somnath":"गिर सोमनाथ","Jamnagar":"जामनगर","Junagadh":"जूनागढ़",
 "Kheda":"खेड़ा","Kutch":"कच्छ","Mahisagar":"महीसागर","Mehsana":"महसाणा",
 "Morbi":"मोरबी","Narmada":"नर्मदा","Navsari":"नवसारी","Panchmahal":"पंचमहाल",
 "Patan":"पाटन","Porbandar":"पोरबंदर","Rajkot":"राजकोट","Sabarkantha":"साबरकांठा",
 "Surat":"सूरत","Surendranagar":"सुरेंद्रनगर","Tapi":"तापी","Vadodara":"वडोदरा",
 "Valsad":"वलसाड",
 "Devbhumi Dwarka":"देवभूमि द्वारका",
 "Vav-Tharad":"वाव-थराद"
}

JHARKHAND_HINDI = {
 "Bokaro":"बोकारो","Chatra":"चतरा","Deoghar":"देवघर","Dhanbad":"धनबाद",
 "Dumka":"दुमका","East Singhbhum":"पूर्वी सिंहभूम","Garhwa":"गढ़वा","Giridih":"गिरिडीह",
 "Godda":"गोड्डा","Gumla":"गुमला","Hazaribagh":"हजारीबाग","Jamtara":"जामताड़ा",
 "Khunti":"खूंटी","Koderma":"कोडरमा","Latehar":"लातेहार","Lohardaga":"लोहरदगा",
 "Pakur":"पाकुड़","Palamu":"पलामू","Ramgarh":"रामगढ़","Ranchi":"रांची",
 "Sahibganj":"साहिबगंज","Seraikela Kharsawan":"सरायकेला खरसावां","Simdega":"सिमडेगा","West Singhbhum":"पश्चिमी सिंहभूम",
 "Saraikela-Kharsawan":"सरायकेला-खरसावां"
}

UTTARAKHAND_HINDI = {
 "Almora":"अल्मोड़ा","Bageshwar":"बागेश्वर","Chamoli":"चमोली","Champawat":"चंपावत",
 "Dehradun":"देहरादून","Haridwar":"हरिद्वार","Nainital":"नैनीताल","Pauri Garhwal":"पौड़ी गढ़वाल",
 "Pithoragarh":"पिथौरागढ़","Rudraprayag":"रुद्रप्रयाग","Tehri Garhwal":"टिहरी गढ़वाल",
 "Udham Singh Nagar":"उधम सिंह नगर","Uttarkashi":"उत्तरकाशी"
}

HP_HINDI = {
 "Bilaspur":"बिलासपुर","Chamba":"चंबा","Hamirpur":"हमीरपुर","Kangra":"कांगड़ा",
 "Kinnaur":"किन्नौर","Kullu":"कुल्लू","Lahaul and Spiti":"लाहुल और स्पीति",
 "Mandi":"मंडी","Shimla":"शिमला","Sirmaur":"सिरमौर","Solan":"सोलन","Una":"ऊना"
}

KARNATAKA_HINDI = {
 "Bagalkot":"बागलकोट","Ballari":"बल्लारी","Belagavi":"बेलगावी","Bengaluru Rural":"बेंगलुरु ग्रामीण",
 "Bengaluru Urban":"बेंगलुरु शहरी","Bidar":"बीदर","Chamarajanagar":"चामराजनगर","Chikkaballapur":"चिक्कबल्लापुर",
 "Chikkamagaluru":"चिक्कमगलुरु","Chitradurga":"चित्रदुर्ग","Dakshina Kannada":"दक्षिण कन्नड़","Davanagere":"दावणगेरे",
 "Dharwad":"धारवाड़","Gadag":"गदग","Hassan":"हासन","Haveri":"हावेरी",
 "Kalaburagi":"कलबुर्गी","Kodagu":"कोडागु","Kolar":"कोलार","Koppal":"कोप्पल",
 "Mandya":"मंड्या","Mysuru":"मैसूरु","Raichur":"रायचूर","Ramanagara":"रामनगर",
 "Shivamogga":"शिवमोग्गा","Tumakuru":"तुमकुरु","Udupi":"उडुपी","Uttara Kannada":"उत्तर कन्नड़",
 "Vijayapura":"विजयपुर","Yadgir":"यादगीर",
 "Bagalkote":"बागलकोट",
 "Chamarajanagara":"चामराजनगर",
 "Chikkaballapura":"चिक्कबल्लापुर"
}

WB_HINDI = {
 "Alipurduar":"अलीपुरद्वार","Bankura":"बांकुड़ा","Birbhum":"बीरभूम","Cooch Behar":"कोच बिहार",
 "Dakshin Dinajpur":"दक्षिण दिनाजपुर","Darjeeling":"दार्जिलिंग","Hooghly":"हुगली","Howrah":"हावड़ा",
 "Jalpaiguri":"जलपाईगुड़ी","Jhargram":"झारग्राम","Kalimpong":"कालिम्पोंग","Kolkata":"कोलकाता",
 "Malda":"मालदा","Murshidabad":"मुलशिदाबाद","Nadia":"नदिया","North 24 Parganas":"उत्तर 24 परगना",
 "Paschim Bardhaman":"पश्चिम बर्धमान","Paschim Medinipur":"पश्चिम मेदिनीपुर","Purba Bardhaman":"पूर्व बर्धमान",
 "Purba Medinipur":"पूर्व मेदिनीपुर","Purulia":"पुरुलिया","South 24 Parganas":"दक्षिण 24 परगना","Uttar Dinajpur":"उत्तर दिनाजपुर"
}

ODISHA_HINDI = {
 "Angul":"अनुगुल","Balangir":"बलांगिर","Balasore":"बालेश्वर","Bargarh":"बरगढ़",
 "Bhadrak":"भद्रक","Baudh":"बौध","Cuttack":"कटक","Deogarh":"देवगढ़",
 "Dhenkanal":"ढेंकानाल","Gajapati":"गजपति","Ganjam":"गंजाम","Jagatsinghpur":"जगतसिंहपुर",
 "Jajpur":"जाजपुर","Jharsuguda":"झारसुगुड़ा","Kalahandi":"कालाहांडी","Kandhamal":"कंधमाल",
 "Kendrapara":"केंद्रपाड़ा","Kendujhar":"केन्दूझर","Khordha":"खोर्धा","Koraput":"कोरापुट",
 "Malkangiri":"मलकानगिरी","Mayurbhanj":"मयूरभंज","Nabarangpur":"नबरंगपुर","Nayagarh":"नयागढ़",
 "Nuapada":"नुआपाड़ा","Puri":"पुरी","Rayagada":"रायगड़ा","Sambalpur":"संबलपुर",
 "Subarnapur":"सुवर्णपुर","Sundargarh":"सुंदरगढ़",
 "Boudh":"बौध",
 "Nabarangapur":"नबरंगपुर"
}

AP_HINDI = {
 "Anantapur":"अनंतपुर","Chittoor":"चित्तूर","East Godavari":"पूर्वी गोदावरी","Guntur":"गुंटूर",
 "Krishna":"कृष्णा","Kurnool":"कर्नूल","Prakasam":"प्रकाशम","Srikakulam":"श्रीकाकुलम",
 "Sri Potti Sriramulu Nellore":"नेल्लौर","Visakhapatnam":"विशाखापट्टनम","Vizianagaram":"विज़ियानगरम","West Godavari":"पश्चिमी गोदावरी",
 "Y.S.R. Kadapa":"कडपा",
 "Alluri Sitharama Raju":"अल्लूरी सीतारामाराजू",
 "Anakapalli":"अनकापल्ली",
 "Anantapuramu":"अनंतपुरम",
 "Annamayya":"अन्नमय्या",
 "Bapatla":"बापटला",
 "Eluru":"एलुरु",
 "Kakinada":"काकीनाडा",
 "Konaseema":"कोनसीमा",
 "NTR":"एनटीआर",
 "Nandyal":"नंद्याल",
 "Palnadu":"पलनाडु",
 "Parvathipuram Manyam":"पार्वतीपुरम मान्यम",
 "Sri Sathya Sai":"श्री सत्य साई",
 "Tirupati":"तिरुपति",
 "YSR":"वाईएसआर कडपा"
}

TELANGANA_HINDI = {
 "Adilabad":"आदिलाबाद","Bhadradri Kothagudem":"भद्राद्री कोठागुडेम","Hyderabad":"हैदराबाद","Jtial":"जगित्याल",
 "Jangaon":"जनगांव","Jayashankar Bhupalpally":"जयशंकर भूपालपल्ली","Jogulamba Gadwal":"जोगुलाम्बा गद्वाल","Kamareddy":"कामारेड्डी",
 "Karimnagar":"करीमनगर","Khammam":"खम्मम","Kumuram Bheem Asifabad":"कोमराम भीम आसिफाबाद","Mahabubabad":"महबूबाबाद",
 "Mahabubnagar":"महबूबनगर","Mancherial":"मंचेरियल","Medak":"मेडक","Medchal Malkajgiri":"मेडचल मलकाजगिरि",
 "Mulugu":"मुलुगु","Nagarkurnool":"नागरकर्नूल","Nalgonda":"नलगोंडा","Narayanpet":"नारायणपेट",
 "Nirmal":"निर्माला","Nizamabad":"निज़ामाबाद","Peddapalli":"पेद्दापल्ली","Rajanna Sircilla":"राजन्ना सिरसिल्ला",
 "Ranga Reddy":"रंगा रेड्डी","Sangareddy":"संगारेड्डी","Siddipet":"सिद्दिपेट","Suryapet":"सूर्यापेट",
 "Vikarabad":"विकाराबाद","Wanaparthy":"वनपर्ति","Warangal Rural":"वारंगल ग्रामीण","Warangal Urban":"वारंगल शहरी",
 "Yadadri Bhuvanagiri":"यादाद्री भुवनगिरि",
 "Jagtial":"जगतियाल",
 "Jayashankar Bhupalapally":"जयशंकर भूपालपल्ली",
 "Komaram Bheem":"कोमाराम भीम"
}

TN_HINDI = {
 "Ariyalur":"अरियालूर","Chengalpattu":"चेंगलपट्टू","Chennai":"चेन्नई","Coimbatore":"कोयंबटूर",
 "Cuddalore":"कडलूर","Dharmapuri":"धर्मपुरी","Dindigul":"डिंडीगुल","Erode":"इरोड",
 "Kallakurichi":"कल्लाकुरुचि","Kanchipuram":"कांचीपुरम","Kanyakumari":"कन्याकुमारी","Karur":"करूर",
 "Krishnagiri":"कृष्णगिरि","Madurai":"मदुरै","Mayiladuthurai":"मइलादुतुरै","Nagapattinam":"नागपट्टिनम",
 "Namakkal":"नामक्कल","Nilgiris":"नीलगिरि","Perambalur":"पेरम्बलूर","Pudukkottai":"पुदुक्कोट्टै",
 "Ramanathapuram":"रामनाथपुरम","Ranipet":"राणीपेट","Salem":"सेलम","Sivaganga":"शिवगंगा",
 "Tenkasi":"तेनकासी","Thanjavur":"तंजावुर","Theni":"थेनी","Thoothukudi":"थूथुकुडी",
 "Tiruchirappalli":"तिरुचिरापल्ली","Tirunelveli":"तिरुनेलवेली","Tirupathur":"तिरुपात्तूर","Tiruppur":"तिरुपुर",
 "Tiruvallur":"तिरुवल्लूर","Tiruvannamalai":"तिरुवन्नमलाई","Tiruvarur":"तिरुवारूर","Vellore":"वेल्लूर",
 "Viluppuram":"विल्लुपुरम","Virudhunagar":"विरुधुनगर",
 "Kancheepuram":"कांचीपुरम",
 "Thiruvallur":"तिरुवल्लूर",
 "Thiruvarur":"तिरुवारूर",
 "Thoothukkudi":"थूथुकुडी"
}

KERALA_HINDI = {
 "Alappuzha":"आलेप्पी (अलप्पुझा)","Ernakulam":"एर्नाकुलम","Idukki":"इडुक्की","Kannur":"कन्नूर",
 "Kasaragod":"कासरगोड","Kollam":"कोल्लम","Kottayam":"कोट्टायम","Kozhikode":"कोड़िकोड",
 "Malappuram":"मलप्पुरम","Palakkad":"पालक्काड","Pathanamthitta":"पथानमतिट्टा","Thiruvananthapuram":"तिरुवनंतपुरम",
 "Thrissur":"त्रिशूर","Wayanad":"वायनाड"
}

ASSAM_HINDI = {
 "Baksa":"बक्सा","Barpeta":"बरपेटा","Biswanath":"विश्वनाथ","Bongaigaon":"बोंगाईगांव",
 "Cachar":"कछार","Charaideo":"चराइदेव","Chirang":"चिरांग","Darrang":"दरंग",
 "Dhemaji":"धेमाजी","Dhubri":"धुबरी","Dibrugarh":"डिब्रूगढ़","Dima Hasao":"डिमा हसाओ",
 "Goalpara":"ग्वालपारा","Golaghat":"गोलाघाट","Hailakandi":"हैलाकांडी","Hojai":"होजाई",
 "Jorhat":"जोरहाट","Kamrup":"कामरूप","Kamrup Metropolitan":"कामरूप मेट्रो","Karbi Anglong":"कारबी आंगलोंग",
 "Karimganj":"करीमगंज","Kokrajhar":"कोकराझार","Lakhimpur":"लखीमपुर","Majuli":"माजुली",
 "Morigaon":"मोरीगांव","Nagaon":"नगांव","Nalbari":"नलबाड़ी","Sivasagar":"शिवसागर",
 "Sonitpur":"शोणितपुर","South Salmara-Mankachar":"दक्षिण सालमारा-मानकाचर","Tinsukia":"तिनसुकिया","Udalguri":"उदालगुड़ी",
 "West Karbi Anglong":"पश्चिम कारबी आंगलोंग",
 "South Salmara Mankachar":"दक्षिण सलमारा-मनकाचर"
}

JK_HINDI = {
 "Anantnag":"अनंतनाग","Bandipora":"बांदीपोरा","Baramulla":"बारामूला","Budgam":"बड़गाम",
 "Doda":"डोडा","Ganderbal":"गांदरबल","Jammu":"जम्मू","Kathua":"कठुआ",
 "Kishtwar":"किश्तवाड़","Kulgam":"कुलगाम","Kupwara":"कुपवाड़ा","Poonch":"पुंछ",
 "Pulwama":"पुलवामा","Rajouri":"राजौरी","Ramban":"रामबन","Reasi":"रियासी",
 "Samba":"सांभा","Shopian":"शोपियां","Srinagar":"श्रीनगर","Udhampur":"उधमपुर",
 "Mirpur":"मीरपुर",
 "Muzaffarabad":"मुजफ्फराबाद",
 "Punch":"पुंछ",
 "Shopiyan":"शोपियां"
}

LADAKH_HINDI = {
 "Kargil":"कारगिल","Leh":"लेह"
}

DELHI_HINDI = {
 "Central Delhi":"मध्य दिल्ली","East Delhi":"पूर्वी दिल्ली","New Delhi":"नई दिल्ली","North Delhi":"उत्तरी दिल्ली",
 "North East Delhi":"उत्तर पूर्वी दिल्ली","North West Delhi":"उत्तर पश्चिमी दिल्ली","Shahdara":"शाहदरा","South Delhi":"दक्षिणी दिल्ली",
 "South East Delhi":"दक्षिण पूर्वी दिल्ली","South West Delhi":"दक्षिण पश्चिमी दिल्ली","West Delhi":"पश्चिमी दिल्ली",
 "Delhi":"दिल्ली"
}

ARUNACHAL_HINDI = {
 "Anjaw":"अंजाव","Changlang":"चांगलांग","Dibang Valley":"दिबांग घाटी","East Kameng":"पूर्वी कामेंग",
 "East Siang":"पूर्वी सियांग","Kamle":"कमले","Kra Daadi":"करा दादी","Kurung Kumey":"कुरुंग कुमे",
 "Lepa Rada":"लेपा राडा","Lhit":"लोहित","Longding":"लोंगडिंग","Lower Dibang Valley":"निचली दिबांग घाटी",
 "Lower Siang":"निचली सियांग","Lower Subansiri":"निचली सुबनसिरी","Namsai":"नामसाई","Pakke Kessang":"पक्के केसांग",
 "Papum Pare":"पापम पारे","Shi Yomi":"शी योमी","Siang":"सियांग","Tawang":"तवांग",
 "Tirap":"तिराप","Upper Siang":"ऊपरी सियांग","Upper Subansiri":"ऊपरी सुबनसिरी","West Kameng":"पश्चिम कामेंग",
 "West Siang":"पश्चिम सियांग",
 "Lohit":"लोहित",
 "Upper Dibang Valley":"ऊपरी दिबांग घाटी"
}

GOA_HINDI = {
 "North Goa":"उत्तर गोवा","South Goa":"दक्षिण गोवा"
}

MANIPUR_HINDI = {
 "Bishnupur":"बिष्णुपुर","Chandel":"चंदेल","Churachandpur":"चुराचांदपुर","Imphal East":"इम्फाल पूर्व",
 "Imphal West":"इम्फाल पश्चिम","Jiribam":"जिरीबाम","Kakching":"काकचिंग","Kamjong":"कामजोंग",
 "Kangpokpi":"कांगपोकपी","Noney":"नोनी","Pherzawl":"फेर्जावल","Senapati":"सेनापति",
 "Tamenglong":"तमेंगलोंग","Tengnoupal":"तेंगनौपाल","Thoubal":"थौबल","Ukhrul":"उख्रुल"
}

MEGHALAYA_HINDI = {
 "East Garo Hills":"पूर्वी गारो हिल्स","East Jaintia Hills":"पूर्वी जयंतिया हिल्स","East Khasi Hills":"पूर्वी खासी हिल्स",
 "North Garo Hills":"उत्तरी गारो हिल्स","Ri Bhoi":"री भोई","South Garo Hills":"दक्षिणी गारो हिल्स",
 "South West Garo Hills":"दक्षिण पश्चिम गारो हिल्स","South West Khasi Hills":"दक्षिण पश्चिम खासी हिल्स","West Garo Hills":"पश्चिम गारो हिल्स",
 "West Jaintia Hills":"पश्चिम जयंतिया हिल्स","West Khasi Hills":"पश्चिम खासी हिल्स",
 "Ribhoi":"री-भोई"
}

MIZORAM_HINDI = {
 "Aizawl":"आइजोल","Champhai":"चम्पाई","Hnahthial":"हनाहथियाल","Khawzawl":"खौजोल",
 "Kolasib":"कोलासिब","Lawngtlai":"लॉंगत्लाई","Lunglei":"लुंगलेई","Mamit":"ममित",
 "Saitual":"सैतुल","Siaha":"सियाहा","Serchhip":"सरछिप",
 "Saiha":"सैहा"
}

NAGALAND_HINDI = {
 "Dimapur":"दीमापुर","Kiphire":"किफिरे","Kohima":"कोहिमा","Longleng":"लोंगलेंग",
 "Mokokchung":"मोकोकचुंग","Mon":"मोन","Peren":"पेरेन","Phek":"फेक",
 "Tuensang":"तुएनसांग","Wokha":"वोखा","Zunheboto":"जुन्हेबोटो"
}

SIKKIM_HINDI = {
 "East Sikkim":"पूर्वी सिक्किम","North Sikkim":"उत्तरी सिक्किम","South Sikkim":"दक्षिणी सिक्किम","West Sikkim":"पश्चिमी सिक्किम"
}

TRIPURA_HINDI = {
 "Dhalai":"धलाई","Gomati":"गोमती","Khowai":"खोवाई","North Tripura":"उत्तरी त्रिपुरा",
 "Sepahijala":"सिपाहीजाला","South Tripura":"दक्षिणी त्रिपुरा","Unakoti":"ऊनाकोटी","West Tripura":"पश्चिमी त्रिपुरा",
 "Sipahijala":"सिपाहीजला",
 "Unokoti":"ऊनाकोटी"
}

ANDAMAN_HINDI = {
 "Nicobar":"निकोबार","North and Middle Andaman":"उत्तर और मध्य अंडमान","South Andaman":"दक्षिण अंडमान",
 "Nicobars":"निकोबार"
}

CHANDIGARH_HINDI = {
 "Chandigarh":"चंडीगढ़"
}

DNH_DD_HINDI = {
 "Daman":"दमन","Diu":"दीव","Dadra and Nagar Haveli":"दादरा और नगर हवेली"
}

LAKSHADWEEP_HINDI = {
 "Lakshadweep":"लक्षद्वीप"
}

PUDUCHERRY_HINDI = {
 "Karaikal":"कराईकल","Mahe":"माहे","Puducherry":"पुडुचेरी","Yanam":"यानम"
}

# One state = one entry. Everything downstream reads this dict: the images here,
# the नक्शा pages and the KM_STATE_MAPS picker list (make_naksha_pages.py), so a
# state added below appears everywhere once both scripts have run.
STATES = {
    "uttar-pradesh": {
        "source":  "uttar-pradesh",
        "geojson": "up-districts.geojson",
        "prefix":  "up-ka-naksha",
        "hi":      "उत्तर प्रदेश",
        "en":      "Uttar Pradesh",
        "kn":      "ಉತ್ತರ ಪ್ರದೇಶ",
        "og_h1":   "उत्तर प्रदेश<br>का नक्शा",
        "page":    "map.html",
        "iso":     "IN-UP",
        "center":  (26.8467, 80.9462),
        "hindi":   UP_HINDI,
    },
    "rajasthan": {
        "source":  "rajasthan",
        "geojson": "rajasthan-districts.geojson",
        "prefix":  "rajasthan-ka-naksha",
        "hi":      "राजस्थान",
        "en":      "Rajasthan",
        "kn":      "ರಾಜಸ್ಥಾನ",
        "og_h1":   "राजस्थान<br>का नक्शा",
        "page":    "rajasthan-ka-naksha.html",
        "iso":     "IN-RJ",
        "center":  (26.9124, 75.7873),
        "note":    "यह नक्शा Census of India की जिला-सीमाओं पर आधारित है, इसलिए 2023 में बने नए जिले "
                   "(ब्यावर, डीग, डीडवाना-कुचामन आदि) अलग से नहीं दिखते — वे अपने मूल जिले के भीतर हैं।",
        "hindi":   RAJ_HINDI,
    },
    "madhya-pradesh": {
        "source":  "madhya-pradesh",
        "geojson": "madhya-pradesh-districts.geojson",
        "prefix":  "madhya-pradesh-ka-naksha",
        "hi":      "मध्य प्रदेश",
        "en":      "Madhya Pradesh",
        "kn":      "ಮಧ್ಯ ಪ್ರದೇಶ",
        "og_h1":   "मध्य प्रदेश<br>का नक्शा",
        "page":    "madhya-pradesh-ka-naksha.html",
        "iso":     "IN-MP",
        "center":  (23.2599, 77.4126),
        "note":    "होशंगाबाद अब नर्मदापुरम कहलाता है — नक्शे में नया नाम ही लिखा है। सीमाएँ Census of "
                   "India की हैं, इसलिए मऊगंज व पांढुर्ना जैसे नए जिले अपने मूल जिले के भीतर हैं।",
        "hindi":   MP_HINDI,
    },
    "bihar": {
        "source":  "bihar",
        "geojson": "bihar-districts.geojson",
        "prefix":  "bihar-ka-naksha",
        "hi":      "बिहार",
        "en":      "Bihar",
        "kn":      "ಬಿಹಾರ",
        "og_h1":   "बिहार<br>का नक्शा",
        "page":    "bihar-ka-naksha.html",
        "iso":     "IN-BR",
        "center":  (25.5941, 85.1376),
        "hindi":   BIHAR_HINDI,
    },
    "maharashtra": {
        "source":  "maharashtra",
        "geojson": "maharashtra-districts.geojson",
        "prefix":  "maharashtra-ka-naksha",
        "hi":      "महाराष्ट्र",
        "en":      "Maharashtra",
        "kn":      "ಮಹಾರಾಷ್ಟ್ರ",
        "og_h1":   "महाराष्ट्र<br>का नक्शा",
        "page":    "maharashtra-ka-naksha.html",
        "iso":     "IN-MH",
        "center":  (19.7515, 75.7139),
        "note":    "औरंगाबाद अब छत्रपति संभाजीनगर और उस्मानाबाद अब धाराशिव है — नक्शे में नए नाम लिखे हैं। "
                   "मुंबई उपनगर Census सीमाओं में मुंबई के भीतर ही है।",
        "hindi":   MH_HINDI,
    },
    "punjab": {
        "source":  "punjab",
        "geojson": "punjab-districts.geojson",
        "prefix":  "punjab-ka-naksha",
        "hi":      "पंजाब",
        "en":      "Punjab",
        "kn":      "ಪಂಜಾಬ್",
        "og_h1":   "पंजाब<br>का नक्शा",
        "page":    "punjab-ka-naksha.html",
        "iso":     "IN-PB",
        "center":  (30.7333, 76.7794),
        "note":    "मोहाली (S.A.S. नगर) और नवांशहर (शहीद भगत सिंह नगर) दोनों नामों से जाने जाते हैं — "
                   "नक्शे में आम बोलचाल का नाम लिखा है। सीमा-डेटा Census of India का है।",
        "hindi":   PUNJAB_HINDI,
    },
    "haryana": {
        "source":  "haryana",
        "geojson": "haryana-districts.geojson",
        "prefix":  "haryana-ka-naksha",
        "hi":      "हरियाणा",
        "en":      "Haryana",
        "kn":      "ಹರಿಯಾಣ",
        "og_h1":   "हरियाणा<br>का नक्शा",
        "page":    "haryana-ka-naksha.html",
        "iso":     "IN-HR",
        "center":  (29.0588, 76.0856),
        "hindi":   HARYANA_HINDI,
    },
    "chhattisgarh": {
        "source":  "chhattisgarh",
        "geojson": "chhattisgarh-districts.geojson",
        "prefix":  "chhattisgarh-ka-naksha",
        "hi":      "छत्तीसगढ़",
        "en":      "Chhattisgarh",
        "kn":      "ಛತ್ತೀಸ್‌ಗಢ",
        "og_h1":   "छत्तीसगढ़<br>का नक्शा",
        "page":    "chhattisgarh-ka-naksha.html",
        "iso":     "IN-CT",
        "center":  (21.2787, 81.8661),
        "hindi":   CHHATTISGARH_HINDI,
    },
    "gujarat": {
        "source":  "gujarat",
        "geojson": "gujarat-districts.geojson",
        "prefix":  "gujarat-ka-naksha",
        "hi":      "गुजरात",
        "en":      "Gujarat",
        "kn":      "ಗುಜರಾತ್",
        "og_h1":   "गुजरात<br>का नक्शा",
        "page":    "gujarat-ka-naksha.html",
        "iso":     "IN-GJ",
        "center":  (23.2156, 72.6369),
        "hindi":   GUJARAT_HINDI,
    },
    "jharkhand": {
        "source":  "jharkhand",
        "geojson": "jharkhand-districts.geojson",
        "prefix":  "jharkhand-ka-naksha",
        "hi":      "झारखंड",
        "en":      "Jharkhand",
        "kn":      "ಜಾರ್ಖಂಡ್",
        "og_h1":   "झारखंड<br>का नक्शा",
        "page":    "jharkhand-ka-naksha.html",
        "iso":     "IN-JH",
        "center":  (23.3441, 85.3096),
        "hindi":   JHARKHAND_HINDI,
    },
    "uttarakhand": {
        "source":  "uttarakhand",
        "geojson": "uttarakhand-districts.geojson",
        "prefix":  "uttarakhand-ka-naksha",
        "hi":      "उत्तराखंड",
        "en":      "Uttarakhand",
        "kn":      "ಉತ್ತರಾಖಂಡ",
        "og_h1":   "उत्तराखंड<br>का नक्शा",
        "page":    "uttarakhand-ka-naksha.html",
        "iso":     "IN-UT",
        "center":  (30.3165, 78.0322),
        "hindi":   UTTARAKHAND_HINDI,
    },
    "himachal-pradesh": {
        "source":  "himachal-pradesh",
        "geojson": "himachal-pradesh-districts.geojson",
        "prefix":  "himachal-pradesh-ka-naksha",
        "hi":      "हिमाचल प्रदेश",
        "en":      "Himachal Pradesh",
        "kn":      "ಹಿಮಾಚಲ ಪ್ರದೇಶ",
        "og_h1":   "हिमाचल प्रदेश<br>का नक्शा",
        "page":    "himachal-pradesh-ka-naksha.html",
        "iso":     "IN-HP",
        "center":  (31.1048, 77.1734),
        "hindi":   HP_HINDI,
    },
    "karnataka": {
        "source":  "karnataka",
        "geojson": "karnataka-districts.geojson",
        "prefix":  "karnataka-ka-naksha",
        "hi":      "कर्नाटक",
        "en":      "Karnataka",
        "kn":      "ಕರ್ನಾಟಕ",
        "og_h1":   "कर्नाटक<br>का नक्शा",
        "page":    "karnataka-ka-naksha.html",
        "iso":     "IN-KA",
        "center":  (12.9716, 77.5946),
        "hindi":   KARNATAKA_HINDI,
    },
    "west-bengal": {
        "source":  "west-bengal",
        "geojson": "west-bengal-districts.geojson",
        "prefix":  "west-bengal-ka-naksha",
        "hi":      "पश्चिम बंगाल",
        "en":      "West Bengal",
        "kn":      "ಪಶ್ಚಿಮ ಬಂಗಾಳ",
        "og_h1":   "पश्चिम बंगाल<br>का नक्शा",
        "page":    "west-bengal-ka-naksha.html",
        "iso":     "IN-WB",
        "center":  (22.5726, 88.3639),
        "hindi":   WB_HINDI,
    },
    "odisha": {
        "source":  "odisha",
        "geojson": "odisha-districts.geojson",
        "prefix":  "odisha-ka-naksha",
        "hi":      "ओडिशा",
        "en":      "Odisha",
        "kn":      "ಒಡಿಶಾ",
        "og_h1":   "ओडिशा<br>का नक्शा",
        "page":    "odisha-ka-naksha.html",
        "iso":     "IN-OR",
        "center":  (20.2961, 85.8245),
        "hindi":   ODISHA_HINDI,
    },
    "andhra-pradesh": {
        "source":  "andhra-pradesh",
        "geojson": "andhra-pradesh-districts.geojson",
        "prefix":  "andhra-pradesh-ka-naksha",
        "hi":      "आंध्र प्रदेश",
        "en":      "Andhra Pradesh",
        "kn":      "ಆಂಧ್ರ ಪ್ರದೇಶ",
        "og_h1":   "आंध्र प्रदेश<br>का नक्शा",
        "page":    "andhra-pradesh-ka-naksha.html",
        "iso":     "IN-AP",
        "center":  (16.5062, 80.6480),
        "hindi":   AP_HINDI,
    },
    "telangana": {
        "source":  "telangana",
        "geojson": "telangana-districts.geojson",
        "prefix":  "telangana-ka-naksha",
        "hi":      "तेलंगाना",
        "en":      "Telangana",
        "kn":      "ತೆಲಂಗಾಣ",
        "og_h1":   "तेलंगाना<br>का नक्शा",
        "page":    "telangana-ka-naksha.html",
        "iso":     "IN-TG",
        "center":  (17.3850, 78.4867),
        "hindi":   TELANGANA_HINDI,
    },
    "tamil-nadu": {
        "source":  "tamil-nadu",
        "geojson": "tamil-nadu-districts.geojson",
        "prefix":  "tamil-nadu-ka-naksha",
        "hi":      "तमिलनाडु",
        "en":      "Tamil Nadu",
        "kn":      "ತಮಿಳುನಾಡು",
        "og_h1":   "तमिलनाडु<br>का नक्शा",
        "page":    "tamil-nadu-ka-naksha.html",
        "iso":     "IN-TN",
        "center":  (13.0827, 80.2707),
        "hindi":   TN_HINDI,
    },
    "kerala": {
        "source":  "kerala",
        "geojson": "kerala-districts.geojson",
        "prefix":  "kerala-ka-naksha",
        "hi":      "केरल",
        "en":      "Kerala",
        "kn":      "ಕೇರಳ",
        "og_h1":   "केरल<br>का नक्शा",
        "page":    "kerala-ka-naksha.html",
        "iso":     "IN-KL",
        "center":  (8.5241, 76.9366),
        "hindi":   KERALA_HINDI,
    },
    "assam": {
        "source":  "assam",
        "geojson": "assam-districts.geojson",
        "prefix":  "assam-ka-naksha",
        "hi":      "असम",
        "en":      "Assam",
        "kn":      "ಅಸ್ಸಾಂ",
        "og_h1":   "असम<br>का नक्शा",
        "page":    "assam-ka-naksha.html",
        "iso":     "IN-AS",
        "center":  (26.1433, 91.7898),
        "hindi":   ASSAM_HINDI,
    },
    "jammu-and-kashmir": {
        "source":  "jammu-and-kashmir",
        "geojson": "jammu-and-kashmir-districts.geojson",
        "prefix":  "jammu-and-kashmir-ka-naksha",
        "hi":      "जम्मू और कश्मीर",
        "en":      "Jammu and Kashmir",
        "kn":      "ಜಮ್ಮು ಮತ್ತು ಕಾಶ್ಮೀರ",
        "og_h1":   "जम्मू और कश्मीर<br>का नक्शा",
        "page":    "jammu-and-kashmir-ka-naksha.html",
        "iso":     "IN-JK",
        "center":  (34.0837, 74.7973),
        "hindi":   JK_HINDI,
    },
    "ladakh": {
        "source":  "ladakh",
        "geojson": "ladakh-districts.geojson",
        "prefix":  "ladakh-ka-naksha",
        "hi":      "लद्दाख",
        "en":      "Ladakh",
        "kn":      "ಲಡಾಖ್",
        "og_h1":   "लद्दाख<br>का नक्शा",
        "page":    "ladakh-ka-naksha.html",
        "iso":     "IN-LA",
        "center":  (34.1526, 77.5771),
        "hindi":   LADAKH_HINDI,
    },
    "delhi": {
        "source":  "delhi",
        "geojson": "delhi-districts.geojson",
        "prefix":  "delhi-ka-naksha",
        "hi":      "दिल्ली",
        "en":      "Delhi",
        "kn":      "ದೆಹಲಿ",
        "og_h1":   "दिल्ली<br>का नक्शा",
        "page":    "delhi-ka-naksha.html",
        "iso":     "IN-DL",
        "center":  (28.6139, 77.2090),
        "hindi":   DELHI_HINDI,
    },
    "arunachal-pradesh": {
        "source":  "arunachal-pradesh",
        "geojson": "arunachal-pradesh-districts.geojson",
        "prefix":  "arunachal-pradesh-ka-naksha",
        "hi":      "अरुणाचल प्रदेश",
        "en":      "Arunachal Pradesh",
        "kn":      "ಅರುಣಾಚಲ ಪ್ರದೇಶ",
        "og_h1":   "अरुणाचल प्रदेश<br>का नक्शा",
        "page":    "arunachal-pradesh-ka-naksha.html",
        "iso":     "IN-AR",
        "center":  (27.0844, 93.6053),
        "hindi":   ARUNACHAL_HINDI,
    },
    "goa": {
        "source":  "goa",
        "geojson": "goa-districts.geojson",
        "prefix":  "goa-ka-naksha",
        "hi":      "गोवा",
        "en":      "Goa",
        "kn":      "ಗೋವಾ",
        "og_h1":   "गोवा<br>का नक्शा",
        "page":    "goa-ka-naksha.html",
        "iso":     "IN-GA",
        "center":  (15.4909, 73.8278),
        "hindi":   GOA_HINDI,
    },
    "manipur": {
        "source":  "manipur",
        "geojson": "manipur-districts.geojson",
        "prefix":  "manipur-ka-naksha",
        "hi":      "मणिपुर",
        "en":      "Manipur",
        "kn":      "ಮಣಿಪುರ",
        "og_h1":   "मणिपुर<br>का नक्शा",
        "page":    "manipur-ka-naksha.html",
        "iso":     "IN-MN",
        "center":  (24.8170, 93.9368),
        "hindi":   MANIPUR_HINDI,
    },
    "meghalaya": {
        "source":  "meghalaya",
        "geojson": "meghalaya-districts.geojson",
        "prefix":  "meghalaya-ka-naksha",
        "hi":      "मेघालय",
        "en":      "Meghalaya",
        "kn":      "ಮೇಘಾಲಯ",
        "og_h1":   "मेघालय<br>का नक्शा",
        "page":    "meghalaya-ka-naksha.html",
        "iso":     "IN-ML",
        "center":  (25.5788, 91.8933),
        "hindi":   MEGHALAYA_HINDI,
    },
    "mizoram": {
        "source":  "mizoram",
        "geojson": "mizoram-districts.geojson",
        "prefix":  "mizoram-ka-naksha",
        "hi":      "मिजोरम",
        "en":      "Mizoram",
        "kn":      "ಮಿಜೋರಾಂ",
        "og_h1":   "मिजोरम<br>का नक्शा",
        "page":    "mizoram-ka-naksha.html",
        "iso":     "IN-MZ",
        "center":  (23.7271, 92.7176),
        "hindi":   MIZORAM_HINDI,
    },
    "nagaland": {
        "source":  "nagaland",
        "geojson": "nagaland-districts.geojson",
        "prefix":  "nagaland-ka-naksha",
        "hi":      "नागालैंड",
        "en":      "Nagaland",
        "kn":      "ನಾಗಾಲ್ಯಾಂಡ್",
        "og_h1":   "नागालैंड<br>का नक्शा",
        "page":    "nagaland-ka-naksha.html",
        "iso":     "IN-NL",
        "center":  (25.6751, 94.1086),
        "hindi":   NAGALAND_HINDI,
    },
    "sikkim": {
        "source":  "sikkim",
        "geojson": "sikkim-districts.geojson",
        "prefix":  "sikkim-ka-naksha",
        "hi":      "सिक्किम",
        "en":      "Sikkim",
        "kn":      "ಸಿಕ್ಕಿಂ",
        "og_h1":   "सिक्किम<br>का नक्शा",
        "page":    "sikkim-ka-naksha.html",
        "iso":     "IN-SK",
        "center":  (27.3389, 88.6065),
        "hindi":   SIKKIM_HINDI,
    },
    "tripura": {
        "source":  "tripura",
        "geojson": "tripura-districts.geojson",
        "prefix":  "tripura-ka-naksha",
        "hi":      "त्रिपुरा",
        "en":      "Tripura",
        "kn":      "ತ್ರಿಪುರಾ",
        "og_h1":   "त्रिपुरा<br>का नक्शा",
        "page":    "tripura-ka-naksha.html",
        "iso":     "IN-TR",
        "center":  (23.8315, 91.2868),
        "hindi":   TRIPURA_HINDI,
    },
    "andaman-and-nicobar-islands": {
        "source":  "andaman-and-nicobar-islands",
        "geojson": "andaman-and-nicobar-islands-districts.geojson",
        "prefix":  "andaman-and-nicobar-islands-ka-naksha",
        "hi":      "अंडमान और निकोबार",
        "en":      "Andaman and Nicobar",
        "kn":      "ಅಂಡಮಾನ್ ಮತ್ತು ನಿಕೋಬಾರ್",
        "og_h1":   "अंडमान व निकोबार<br>का नक्शा",
        "page":    "andaman-and-nicobar-islands-ka-naksha.html",
        "iso":     "IN-AN",
        "center":  (11.6234, 92.7265),
        "hindi":   ANDAMAN_HINDI,
    },
    "chandigarh": {
        "source":  "chandigarh",
        "geojson": "chandigarh-districts.geojson",
        "prefix":  "chandigarh-ka-naksha",
        "hi":      "चंडीगढ़",
        "en":      "Chandigarh",
        "kn":      "ಚಂಡೀಗಢ",
        "og_h1":   "चंडीगढ़<br>का नक्शा",
        "page":    "chandigarh-ka-naksha.html",
        "iso":     "IN-CH",
        "center":  (30.7333, 76.7794),
        "hindi":   CHANDIGARH_HINDI,
    },
    "dnh-and-dd": {
        "source":  "dnh-and-dd",
        "geojson": "dnh-and-dd-districts.geojson",
        "prefix":  "dnh-and-dd-ka-naksha",
        "hi":      "दादरा और नगर हवेली एवं दमन और दीव",
        "en":      "Dadra and Nagar Haveli and Daman and Diu",
        "kn":      "ದಾದ್ರಾ ಮತ್ತು ನಗರ ಹವೇಲಿ",
        "og_h1":   "दमन, दीव व दादरा<br>का नक्शा",
        "page":    "dnh-and-dd-ka-naksha.html",
        "iso":     "IN-DH",
        "center":  (20.4283, 72.8397),
        "hindi":   DNH_DD_HINDI,
    },
    "lakshadweep": {
        "source":  "lakshadweep",
        "geojson": "lakshadweep-districts.geojson",
        "prefix":  "lakshadweep-ka-naksha",
        "hi":      "लक्षद्वीप",
        "en":      "Lakshadweep",
        "kn":      "ಲಕ್ಷದ್ವೀಪ",
        "og_h1":   "लक्षद्वीप<br>का नक्शा",
        "page":    "lakshadweep-ka-naksha.html",
        "iso":     "IN-LD",
        "center":  (10.5667, 72.6417),
        "hindi":   LAKSHADWEEP_HINDI,
    },
    "puducherry": {
        "source":  "puducherry",
        "geojson": "puducherry-districts.geojson",
        "prefix":  "puducherry-ka-naksha",
        "hi":      "पुडुचेरी",
        "en":      "Puducherry",
        "kn":      "ಪುದುಚೇರಿ",
        "og_h1":   "पुडुचेरी<br>का नक्शा",
        "page":    "puducherry-ka-naksha.html",
        "iso":     "IN-PY",
        "center":  (11.9416, 79.8083),
        "hindi":   PUDUCHERRY_HINDI,
    },
}


GREEN_DARK, GREEN_MID, GREEN_LIGHT, GREEN_PALE, AMBER = "#1a3c2e", "#2d6a4f", "#52b788", "#d8f3dc", "#e9a825"


def load_and_minify(cfg, scratch):
    raw = scratch / f"{cfg['source']}-raw.geojson"
    if not raw.exists():
        urllib.request.urlretrieve(RAW_URL.format(source=cfg["source"]), raw)
    g = json.load(open(raw, encoding="utf-8"))
    hindi = cfg["hindi"]
    feats = []
    for f in g["features"]:
        name = f["properties"]["district"]
        assert name in hindi, f"no Hindi name for {name}"
        geom = f["geometry"]

        def rnd(ring):
            out, prev = [], None
            for x, y in ring:
                p = [round(x, 4), round(y, 4)]
                if p != prev:
                    out.append(p)
                prev = p
            return out

        if geom["type"] == "Polygon":
            coords = [rnd(r) for r in geom["coordinates"]]
        else:
            coords = [[rnd(r) for r in poly] for poly in geom["coordinates"]]
        feats.append({"type": "Feature",
                      "properties": {"district": name, "district_hi": hindi[name]},
                      "geometry": {"type": geom["type"], "coordinates": coords}})
    out = {"type": "FeatureCollection", "features": feats}
    out_geo = OUT_DIR / cfg["geojson"]
    out_geo.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_geo, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("geojson:", out_geo, os.path.getsize(out_geo), "bytes")
    return out


def rings_of(geom):
    if geom["type"] == "Polygon":
        yield from geom["coordinates"]
    else:
        for poly in geom["coordinates"]:
            yield from poly


def outer_rings(geom):
    if geom["type"] == "Polygon":
        yield geom["coordinates"][0]
    else:
        for poly in geom["coordinates"]:
            yield poly[0]


def shoelace(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-12:
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    a *= 0.5
    return abs(a), cx / (6 * a), cy / (6 * a)


def aspect_of(data):
    """height / width of the state as it will be drawn.

    Needed before any width is chosen: the frame was tuned on UP and Rajasthan,
    which are both roughly as tall as they are wide. A tall-and-narrow state
    (पंजाब, हरियाणा) at the same 1340px width would come out over 2000px tall —
    a download twice the size of the others for no extra detail.
    """
    lons = [x for f in data["features"] for r in rings_of(f["geometry"]) for x, _ in r]
    lats = [y for f in data["features"] for r in rings_of(f["geometry"]) for _, y in r]
    klat = math.cos(math.radians((min(lats) + max(lats)) / 2))
    return (max(lats) - min(lats)) / ((max(lons) - min(lons)) * klat)


def build_svg(data, map_w, label_scale=1.0, labels=True):
    lons = [x for f in data["features"] for r in rings_of(f["geometry"]) for x, _ in r]
    lats = [y for f in data["features"] for r in rings_of(f["geometry"]) for _, y in r]
    lo_x, hi_x, lo_y, hi_y = min(lons), max(lons), min(lats), max(lats)
    klat = math.cos(math.radians((lo_y + hi_y) / 2))
    scale = map_w / ((hi_x - lo_x) * klat)
    map_h = (hi_y - lo_y) * scale

    def px(lon, lat):
        return ((lon - lo_x) * klat * scale, (hi_y - lat) * scale)

    paths, lbls = [], []
    for f in data["features"]:
        d = []
        for ring in rings_of(f["geometry"]):
            pts = [px(x, y) for x, y in ring]
            d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
        paths.append(f'<path d="{"".join(d)}" fill="{GREEN_PALE}" stroke="{GREEN_MID}" stroke-width="1.1"/>')
        if not labels:
            continue
        best = max((shoelace(r) for r in outer_rings(f["geometry"])), key=lambda t: t[0])
        area, cx, cy = best
        x, y = px(cx, cy)
        name = f["properties"]["district_hi"]
        # px area of the district drives label size
        apx = area * (klat * scale) * scale
        size = max(10.5, min(14.5, 7 + math.sqrt(apx) / 22)) * label_scale
        est_w = len(name) * size * 0.62
        dist_w = math.sqrt(apx) * 1.15
        halo = 'stroke="#ffffff" stroke-width="3" paint-order="stroke" stroke-linejoin="round"'
        if est_w > dist_w and " " in name:
            words = name.split(" ")
            mid = len(words) // 2 + len(words) % 2
            l1, l2 = " ".join(words[:mid]), " ".join(words[mid:])
            lbls.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size:.1f}" {halo}>'
                        f'<tspan x="{x:.0f}" dy="-{size*0.15:.0f}">{l1}</tspan>'
                        f'<tspan x="{x:.0f}" dy="{size*1.1:.0f}">{l2}</tspan></text>')
        else:
            lbls.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size:.1f}" {halo}>{name}</text>')
    return "".join(paths), "".join(lbls), map_w, map_h


FONT = "'Nirmala UI','Noto Sans Devanagari','Mangal',sans-serif"


@lru_cache(maxsize=1)
def logo_uri():
    """The कृषि मित्र emblem as a data: URI.

    Inlined rather than linked: the page being screenshotted is written to a
    temp dir, so a relative path can't reach frontend/assets and Chromium
    won't reliably load a file:// subresource from outside that dir.
    """
    return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()


def brand_mark(px=78, on_dark=False, url=False):
    """The कृषि मित्र lockup — emblem + wordmark. Returns (css, html).

    Single source for every generated image: the full district map and the og
    card both render this, so a state added to STATES later is branded without
    anyone remembering to do it. Only the palette flips between the white map
    and the dark og card — the mark itself never diverges.
    """
    ring = "rgba(255,255,255,.20)" if on_dark else GREEN_PALE
    word = "#ffffff" if on_dark else GREEN_DARK
    css = f"""
      .mark{{display:flex;align-items:center;gap:16px;flex-shrink:0}}
      .mark img{{width:{px}px;height:{px}px;border-radius:50%;object-fit:cover;
                box-shadow:0 0 0 4px {ring}}}
      .mark .mt{{font-size:{px * .40:.0f}px;font-weight:700;color:{word};
                letter-spacing:.3px;line-height:1.1}}
      .mark .mu{{font-size:{px * .28:.0f}px;font-weight:700;color:{AMBER};margin-top:3px}}"""
    sub = '<div class="mu">krashimitra.in</div>' if url else ""
    html = (f'<div class="mark"><img src="{logo_uri()}" alt="">'
            f'<div><div class="mt">कृषि मित्र</div>{sub}</div></div>')
    return css, html


def render(html_path, png_path, w, h):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.goto(html_path.resolve().as_uri())
        page.wait_for_timeout(400)
        page.screenshot(path=str(png_path))
        b.close()
    print("png:", png_path, os.path.getsize(png_path), "bytes")


def build_state(key):
    cfg = STATES[key]
    scratch = Path(tempfile.mkdtemp(prefix=f"{key}_map_"))
    data = load_and_minify(cfg, scratch)
    n = len(data["features"])
    hi, prefix = cfg["hi"], cfg["prefix"]
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # ── full labeled map ──
    # The map is a free HD download that gets reshared off-site, so it travels
    # with the mark on it.
    mark_css, mark_html = brand_mark(px=78)
    ratio = aspect_of(data)
    map_w = 1340 if ratio * 1340 <= 1500 else int(1500 / ratio)
    paths, lbls, mw, mh = build_svg(data, map_w=map_w)
    W, H = 1440, int(mh) + 190
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      *{{margin:0;padding:0}} body{{width:{W}px;height:{H}px;background:#fff;font-family:{FONT}}}
      .head{{padding:26px 50px 10px;display:flex;align-items:center;justify-content:space-between;gap:40px}}
      h1{{font-size:34px;color:{GREEN_DARK};font-weight:700}}
      h1 span{{color:{AMBER}}} .sub{{font-size:17px;color:{GREEN_MID};margin-top:4px}}
      .bar{{width:110px;height:5px;background:{AMBER};border-radius:3px;margin-top:10px}}{mark_css}
      svg text{{fill:{GREEN_DARK};font-family:{FONT};text-anchor:middle;font-weight:600}}
      .foot{{position:absolute;bottom:12px;left:50px;right:50px;display:flex;justify-content:space-between;
             font-size:13px;color:#7a8a80}} .foot b{{color:{GREEN_MID}}}
    </style></head><body>
      <div class="head">
        <div><h1>{hi} का नक्शा <span>— {n} जिले</span></h1>
        <div class="sub">जिलेवार मानचित्र • हर जिले का मंडी भाव व मौसम krashimitra.in पर</div><div class="bar"></div></div>
        {mark_html}
      </div>
      <div style="padding:6px 50px 0;text-align:center"><svg width="{mw:.0f}" height="{mh:.0f}" viewBox="0 0 {mw:.0f} {mh:.0f}">{paths}{lbls}</svg></div>
      <div class="foot"><span><b>krashimitra.in</b> — किसानों का साथी</span>
      <span>सीमा-डेटा: Census of India (india-maps-data)</span></div>
    </body></html>"""
    fp = scratch / f"{key}_map_full.html"
    fp.write_text(html, encoding="utf-8")
    render(fp, IMG_DIR / f"{prefix}-district-map.png", W, H)

    # ── og card 1200x630 ──
    # Same lockup, dark palette — it absorbs the old plain-text krashimitra.in line.
    og_mark_css, og_mark_html = brand_mark(px=76, on_dark=True, url=True)
    paths2, _, mw2, mh2 = build_svg(data, map_w=560 if ratio <= 1 else int(560 / ratio),
                                    labels=False)
    html_og = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      *{{margin:0;padding:0}} body{{width:1200px;height:630px;background:{GREEN_DARK};font-family:{FONT};
        display:flex;align-items:center;overflow:hidden}}
      .l{{flex:1;padding:0 20px 0 64px}} h1{{font-size:58px;color:#fff;line-height:1.15;font-weight:700}}
      .sub{{font-size:26px;color:{GREEN_PALE};margin-top:18px}} .bar{{width:120px;height:6px;background:{AMBER};
        border-radius:3px;margin:26px 0}}{og_mark_css}
      .r{{width:600px;height:630px;display:flex;align-items:center;justify-content:center}}
      .r svg{{filter:drop-shadow(0 8px 24px rgba(0,0,0,.35))}}
    </style></head><body>
      <div class="l"><h1>{cfg["og_h1"]}</h1><div class="sub">{n} जिलों का जिलेवार मानचित्र</div>
      <div class="bar"></div>{og_mark_html}</div>
      <div class="r"><svg width="{mw2:.0f}" height="{mh2:.0f}" viewBox="0 0 {mw2:.0f} {mh2:.0f}"
        style="max-height:580px">{paths2.replace(GREEN_PALE, GREEN_LIGHT).replace(GREEN_MID, GREEN_DARK)}</svg></div>
    </body></html>"""
    fo = scratch / f"{key}_map_og.html"
    fo.write_text(html_og, encoding="utf-8")
    render(fo, IMG_DIR / f"{prefix}-og.png", 1200, 630)

    # ── light webp for in-page display ──
    from PIL import Image
    im = Image.open(IMG_DIR / f"{prefix}-district-map.png")
    im.save(IMG_DIR / f"{prefix}-district-map.webp", "WEBP", quality=82, method=6)
    print("webp:", os.path.getsize(IMG_DIR / f"{prefix}-district-map.webp"), "bytes")
    print(f"-> {key}: {n} districts, full map {W}x{H}\n")


def main():
    keys = sys.argv[1:] or list(STATES)
    for k in keys:
        if k not in STATES:
            raise SystemExit(f"unknown state {k!r}; known: {', '.join(STATES)}")
        build_state(k)


if __name__ == "__main__":
    main()
