# -*- coding: utf-8 -*-
# ============================================================
# प्रधानमंत्री किसान मान-धन योजना (PM-KMY) — farmers' old-age pension.
#
# Sources (read 2 Oct 2026):
#   • PM-KMY FAQs, pmkisan.gov.in/Documents/PM-KMY - FAQs.pdf — eligibility
#     (18-40, ≤2 ha, land record as on 01.08.2019), exclusions, the full
#     age-wise contribution chart (₹55 at 18 … ₹200 at 40, equal Govt share),
#     LIC as fund manager, PM-Kisan auto-debit option, free CSC enrolment,
#     due-date / quarterly-4-monthly-half-yearly option, default rules
#     (1 month no late fee, dormant after 6 months), death/family-pension rules,
#     no commutation, wrong declaration → own money back without interest.
#   • PM-KMY Operational Guidelines (same site) + vikaspedia / Vision IAS
#     summaries for exit rules: <10 yr → own share + SB interest; ≥10 yr before
#     60 → own share + higher of SB or fund interest; disability → spouse may
#     continue or exit.
#   • Official portals checked live: pmkmy.gov.in, maandhan.in (both 200).
#
# LEGAL_RULES §3: a scheme page names the scheme, links the official page,
# never promises eligibility or an amount, never takes applications or fees.
# The ₹3,000 is stated as the scheme's own rule, not our promise. No
# "investment" framing (§1) — contributions are shown, no return is computed.
# ============================================================

SITE = "https://krashimitra.in"

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>भूमिका</h2>
    </div>
    <p>
      सरकारी नौकरी वाले को बुढ़ापे में पेंशन मिलती है, पर खेत में पूरी उम्र लगाने वाले किसान को नहीं। इसी कमी के लिए 2019 में <strong>प्रधानमंत्री किसान मान-धन योजना (PM-KMY)</strong> शुरू हुई। यह छोटे और सीमांत किसानों की <strong>स्वैच्छिक, अंशदान वाली पेंशन योजना</strong> है: किसान हर महीने एक छोटी रकम जमा करता है, <strong>उतनी ही रकम केंद्र सरकार भी जोड़ती है</strong>, और 60 साल की उम्र के बाद योजना के नियम के अनुसार <strong>₹3,000 महीना न्यूनतम पेंशन</strong> का प्रावधान है।
    </p>
    <p>
      ज़्यादातर किसान इस योजना का नाम PM किसान सम्मान निधि (₹6,000 वाली) से मिला देते हैं — दोनों अलग हैं। इस लेख में उम्र के हिसाब से <strong>₹55 से ₹200 महीने</strong> तक की पूरी अंशदान तालिका है, कौन जुड़ सकता है और कौन नहीं, पंजीकरण कहाँ होता है, और <strong>बीच में छोड़ने, किस्त चूकने या मृत्यु होने पर क्या होता है</strong> — जो बातें जुड़ने से पहले जाननी ज़रूरी हैं।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        <strong>KrashiMitra एक निजी वेबसाइट है।</strong> हम इस योजना में पंजीकरण नहीं करते, कोई फ़ीस नहीं लेते और पात्रता तय नहीं करते। आधिकारिक जानकारी <a href="https://pmkmy.gov.in" target="_blank" rel="noopener">pmkmy.gov.in</a> और <a href="https://maandhan.in" target="_blank" rel="noopener">maandhan.in</a> पर है, और पंजीकरण आपके नज़दीकी CSC (जन सेवा केंद्र) पर होता है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 1 ── -->
  <div class="ad-slot leaderboard" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="3367685932" data-format="auto"></div>
    </div>
  </div>

  <!-- WHAT IS IT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔍</span>
      <h2>किसान मान-धन योजना कैसे काम करती है?</h2>
    </div>
    <ul>
      <li><strong>जुड़ने की उम्र:</strong> 18 से 40 साल।</li>
      <li><strong>हर महीने अंशदान:</strong> जुड़ने की उम्र के हिसाब से ₹55 से ₹200 तक। जितनी कम उम्र में जुड़ेंगे, महीने की रकम उतनी कम।</li>
      <li><strong>सरकार का हिस्सा:</strong> किसान जितना जमा करता है, केंद्र सरकार <strong>उतनी ही रकम</strong> पेंशन फ़ंड में अलग से जमा करती है।</li>
      <li><strong>पेंशन:</strong> 60 साल पूरे होने के बाद योजना में ₹3,000 महीना न्यूनतम सुनिश्चित पेंशन का प्रावधान है।</li>
      <li><strong>फ़ंड कौन चलाता है:</strong> भारतीय जीवन बीमा निगम (LIC) पेंशन फ़ंड मैनेजर है और पेंशन का भुगतान वही करता है।</li>
      <li><strong>पति/पत्नी के लिए:</strong> पेंशन मिलते समय किसान की मृत्यु होने पर पति/पत्नी को उस पेंशन का <strong>50% पारिवारिक पेंशन</strong> के रूप में मिलता है।</li>
    </ul>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>PM किसान सम्मान निधि से फ़र्क:</strong> सम्मान निधि में सरकार किसान को साल में ₹6,000 देती है, किसान कुछ जमा नहीं करता। मान-धन में <strong>किसान ख़ुद हर महीने जमा करता है</strong> और बदले में 60 के बाद पेंशन का प्रावधान है। सम्मान निधि की जानकारी के लिए हमारा <a href="/articles/PM-kisan-samman-nidhi">PM किसान सम्मान निधि लेख</a> देखें।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- CONTRIBUTION TABLE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📊</span>
      <h2>उम्र के हिसाब से हर महीने कितना जमा करना है — पूरी तालिका</h2>
    </div>
    <p>यह तालिका योजना के आधिकारिक FAQ से ली गई है। <strong>उम्र वही गिनी जाती है जिस दिन आप जुड़ते हैं</strong>, और यह रकम 60 साल तक नहीं बदलती।</p>
    <table class="article-table">
      <thead>
        <tr><th>जुड़ने की उम्र</th><th>किसान का हिस्सा / महीना</th><th>सरकार का हिस्सा / महीना</th><th>कुल / महीना</th></tr>
      </thead>
      <tbody>
        <tr><td>18 साल</td><td class="healthy">₹55</td><td>₹55</td><td>₹110</td></tr>
        <tr><td>19 साल</td><td>₹58</td><td>₹58</td><td>₹116</td></tr>
        <tr><td>20 साल</td><td>₹61</td><td>₹61</td><td>₹122</td></tr>
        <tr><td>21 साल</td><td>₹64</td><td>₹64</td><td>₹128</td></tr>
        <tr><td>22 साल</td><td>₹68</td><td>₹68</td><td>₹136</td></tr>
        <tr><td>23 साल</td><td>₹72</td><td>₹72</td><td>₹144</td></tr>
        <tr><td>24 साल</td><td>₹76</td><td>₹76</td><td>₹152</td></tr>
        <tr><td>25 साल</td><td>₹80</td><td>₹80</td><td>₹160</td></tr>
        <tr><td>26 साल</td><td>₹85</td><td>₹85</td><td>₹170</td></tr>
        <tr><td>27 साल</td><td>₹90</td><td>₹90</td><td>₹180</td></tr>
        <tr><td>28 साल</td><td>₹95</td><td>₹95</td><td>₹190</td></tr>
        <tr><td>29 साल</td><td>₹100</td><td>₹100</td><td>₹200</td></tr>
        <tr><td>30 साल</td><td>₹105</td><td>₹105</td><td>₹210</td></tr>
        <tr><td>31 साल</td><td>₹110</td><td>₹110</td><td>₹220</td></tr>
        <tr><td>32 साल</td><td>₹120</td><td>₹120</td><td>₹240</td></tr>
        <tr><td>33 साल</td><td>₹130</td><td>₹130</td><td>₹260</td></tr>
        <tr><td>34 साल</td><td>₹140</td><td>₹140</td><td>₹280</td></tr>
        <tr><td>35 साल</td><td>₹150</td><td>₹150</td><td>₹300</td></tr>
        <tr><td>36 साल</td><td>₹160</td><td>₹160</td><td>₹320</td></tr>
        <tr><td>37 साल</td><td>₹170</td><td>₹170</td><td>₹340</td></tr>
        <tr><td>38 साल</td><td>₹180</td><td>₹180</td><td>₹360</td></tr>
        <tr><td>39 साल</td><td>₹190</td><td>₹190</td><td>₹380</td></tr>
        <tr><td>40 साल</td><td class="diseased">₹200</td><td>₹200</td><td>₹400</td></tr>
      </tbody>
    </table>
    <div class="tip-box tip">
      <span class="tip-icon">🧮</span>
      <div class="tip-content">
        <strong>60 साल तक आप कुल कितना जमा करेंगे?</strong> 18 साल में जुड़ने वाला ₹55 × 12 महीने × 42 साल = <strong>₹27,720</strong> जमा करता है। 29 साल में जुड़ने वाला ₹100 × 12 × 31 = <strong>₹37,200</strong>। 40 साल में जुड़ने वाला ₹200 × 12 × 20 = <strong>₹48,000</strong>। इतनी ही रकम सरकार भी अपनी ओर से जमा करती है। जुड़ने में देर करने से महीने की किस्त भी बढ़ती है और आपकी कुल जमा रकम भी।
      </div>
    </div>
    <p>
      किस्त हर महीने उसी तारीख़ को बनती है जिस तारीख़ को आप जुड़े थे। चाहें तो <strong>तिमाही, चार महीने या छह महीने</strong> में एक बार भी जमा करने का विकल्प चुन सकते हैं।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- ELIGIBILITY -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✅</span>
      <h2>कौन जुड़ सकता है और कौन नहीं</h2>
    </div>
    <p>योजना के FAQ के अनुसार ये शर्तें हैं। अंतिम फ़ैसला पंजीकरण के समय सरकारी रिकॉर्ड से होता है, हम किसी की पात्रता की गारंटी नहीं दे सकते।</p>
    <table class="article-table">
      <thead>
        <tr><th>शर्त</th><th>✅ जुड़ सकते हैं</th><th>❌ नहीं जुड़ सकते</th></tr>
      </thead>
      <tbody>
        <tr><td>उम्र</td><td class="healthy">18 से 40 साल</td><td class="diseased">18 से कम या 40 से ज़्यादा</td></tr>
        <tr><td>ज़मीन</td><td class="healthy">अपने नाम खेती की ज़मीन, 2 हेक्टेयर (लगभग 5 एकड़) तक</td><td class="diseased">2 हेक्टेयर से ज़्यादा, या अपने नाम ज़मीन ही नहीं (जैसे बटाईदार)</td></tr>
        <tr><td>भू-अभिलेख</td><td class="healthy">नाम राज्य के भू-अभिलेख में 1 अगस्त 2019 की स्थिति में दर्ज</td><td class="diseased">संस्थागत भू-धारक</td></tr>
        <tr><td>दूसरी पेंशन योजना</td><td class="healthy">किसी अन्य सामाजिक सुरक्षा योजना में नहीं</td><td class="diseased">NPS, ESIC, EPFO के सदस्य; PM श्रम योगी मान-धन या PM लघु व्यापारी मान-धन चुन चुके</td></tr>
        <tr><td>आयकर</td><td class="healthy">पिछले आकलन वर्ष में आयकर नहीं भरा</td><td class="diseased">पिछले आकलन वर्ष में आयकर भरने वाले</td></tr>
        <tr><td>नौकरी / पेशा</td><td class="healthy">मल्टी-टास्किंग स्टाफ / चतुर्थ श्रेणी / ग्रुप-D (सेवारत या रिटायर) जुड़ सकते हैं</td><td class="diseased">केंद्र/राज्य सरकार, PSU, स्थानीय निकाय के नियमित कर्मचारी; पंजीकृत डॉक्टर, इंजीनियर, वकील, CA, आर्किटेक्ट</td></tr>
        <tr><td>पद</td><td>—</td><td class="diseased">वर्तमान/पूर्व मंत्री, सांसद, विधायक, महापौर, ज़िला पंचायत अध्यक्ष, संवैधानिक पद धारक</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        <strong>ग़लत घोषणा भारी पड़ती है।</strong> अगर बाद में पता चले कि किसान पात्र नहीं था, तो उसका अपना जमा पैसा <strong>बिना ब्याज</strong> लौटाया जाता है और सरकार का हिस्सा बंद हो जाता है। इसलिए पंजीकरण से पहले शर्तें ईमानदारी से मिला लें।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 2 ── -->
  <div class="ad-slot responsive" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="4489195916" data-format="auto"></div>
    </div>
  </div>

  <!-- HOW TO ENROL -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📝</span>
      <h2>पंजीकरण कैसे और कहाँ होता है</h2>
    </div>
    <ol>
      <li><strong>नज़दीकी CSC (जन सेवा केंद्र) जाएँ:</strong> योजना के FAQ के अनुसार <strong>CSC पर पंजीकरण बिल्कुल मुफ़्त</strong> है। कोई फ़ीस माँगे तो मना करें। CSC न हो तो ज़िले के राज्य नोडल अधिकारी (कृषि विभाग) के ज़रिए भी पंजीकरण हो सकता है।</li>
      <li><strong>साथ ले जाएँ:</strong> आधार कार्ड, बैंक पासबुक (खाता संख्या और IFSC के लिए) और मोबाइल नंबर। ज़मीन की जानकारी राज्य के भू-अभिलेख से मिलाई जाती है, इसलिए खतौनी/7-12 जैसा कागज़ भी साथ रखें।</li>
      <li><strong>CSC संचालक आपकी जानकारी भरता है:</strong> नाम, जन्म तिथि, बैंक विवरण। <strong>जन्म तिथि बाद में कभी नहीं बदली जा सकती</strong>, इसलिए आधार से मिलाकर सही लिखवाएँ।</li>
      <li><strong>ऑटो-डेबिट फ़ॉर्म पर दस्तख़त:</strong> एक "नामांकन-सह-ऑटो-डेबिट अधिदेश" फ़ॉर्म बनता है, जिससे हर किस्त आपके बैंक खाते से अपने आप कटती है। इस पर आपके दस्तख़त होते हैं।</li>
      <li><strong>पेंशन कार्ड:</strong> फ़ॉर्म अपलोड होने के बाद आपको <strong>किसान पेंशन कार्ड</strong> और एक पेंशन खाता संख्या मिलती है। इसे संभाल कर रखें।</li>
      <li><strong>नामांकित व्यक्ति (nominee):</strong> पति/पत्नी या आश्रित को नॉमिनी ज़रूर बनाएँ, ताकि अनहोनी में पैसा सही हाथ में जाए।</li>
    </ol>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>PM किसान की किस्त से ही अंशदान:</strong> जो किसान PM किसान सम्मान निधि पाते हैं, वे सहमति देकर अपना मान-धन अंशदान <strong>सीधे सम्मान निधि की रकम से</strong> कटवा सकते हैं। तब जेब से अलग पैसा देने की ज़रूरत नहीं पड़ती। यह विकल्प पंजीकरण के समय CSC पर चुनें।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- WHAT IF -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">❓</span>
      <h2>किस्त चूक जाए, योजना छोड़नी हो, या अनहोनी हो जाए — तब क्या?</h2>
    </div>
    <p>जुड़ने से पहले ये नियम जानना ज़रूरी है, क्योंकि 20 से 42 साल तक का साथ है।</p>
    <table class="article-table">
      <thead>
        <tr><th>स्थिति</th><th>क्या होता है (योजना के नियम)</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>खाते में पैसा न होने से किस्त कटी नहीं</strong></td><td>पहली छूटी किस्त से 1 महीने तक कोई लेट-फ़ीस नहीं। उसके बाद बकाया पर सरकार द्वारा तय ब्याज/लेट-फ़ीस लगता है।</td></tr>
        <tr><td><strong>6 महीने तक किस्त नहीं भरी</strong></td><td>खाता "निष्क्रिय (dormant)" हो जाता है। बाद में पूरा बकाया ब्याज सहित भरकर फिर चालू कराया जा सकता है।</td></tr>
        <tr><td><strong>10 साल से पहले योजना छोड़ी</strong></td><td>सिर्फ़ <strong>आपका अपना जमा हिस्सा</strong> बचत खाते के ब्याज के साथ लौटता है। सरकार का हिस्सा नहीं मिलता।</td></tr>
        <tr><td><strong>10 साल के बाद, पर 60 से पहले छोड़ी</strong></td><td>आपका अपना हिस्सा, साथ में फ़ंड का कमाया ब्याज या बचत खाते का ब्याज — जो ज़्यादा हो।</td></tr>
        <tr><td><strong>60 से पहले किसान की मृत्यु</strong></td><td>पति/पत्नी चाहें तो बाकी किस्तें भरकर योजना जारी रख सकते हैं, या अपना जमा हिस्सा ब्याज सहित लेकर बाहर निकल सकते हैं। पति/पत्नी न हों तो रकम नॉमिनी को।</td></tr>
        <tr><td><strong>60 से पहले स्थायी विकलांगता</strong></td><td>पति/पत्नी योजना जारी रख सकते हैं, या जमा हिस्सा ब्याज सहित लेकर निकल सकते हैं।</td></tr>
        <tr><td><strong>पेंशन मिलते समय किसान की मृत्यु</strong></td><td>पति/पत्नी को पेंशन का <strong>50%</strong> पारिवारिक पेंशन। दोनों के बाद जमा रकम फ़ंड में लौट जाती है।</td></tr>
        <tr><td><strong>पेंशन एकमुश्त लेना (commutation)</strong></td><td>इसका कोई प्रावधान नहीं है। पेंशन हर महीने ही मिलती है।</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        ब्याज की दर, लेट-फ़ीस और नियम समय-समय पर सरकार बदल सकती है। अपने खाते की स्थिति और ताज़ा नियम <a href="https://maandhan.in" target="_blank" rel="noopener">maandhan.in</a>, अपने CSC या बैंक शाखा से ही पूछें। ऊपर की बातें योजना के FAQ और दिशानिर्देशों का सार हैं, कानूनी सलाह नहीं।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- MISTAKES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚫</span>
      <h2>ये गलतियाँ कभी न करें</h2>
    </div>
    <ul>
      <li><strong>"PM किसान" और "मान-धन" को एक समझना</strong> — एक में पैसा मिलता है, दूसरे में आप जमा करते हैं। फ़ॉर्म भरते समय साफ़ पूछें कि कौन सी योजना है।</li>
      <li><strong>पंजीकरण के लिए किसी को पैसे देना</strong> — CSC पर पंजीकरण मुफ़्त है। "पेंशन पक्की करवा देंगे" कहकर पैसे माँगने वाले से दूर रहें।</li>
      <li><strong>अपना OTP, ATM पिन या बैंक पासवर्ड किसी को बताना</strong> — कोई सरकारी कर्मचारी फ़ोन पर ये नहीं माँगता।</li>
      <li><strong>ग़लत जन्म तिथि लिखवाना</strong> — यह बाद में बदली नहीं जा सकती और इसी से आपकी किस्त तय होती है।</li>
      <li><strong>खाते में बैलेंस न रखना</strong> — ऑटो-डेबिट फ़ेल होगा, किस्त छूटेगी और बाद में ब्याज लगेगा। किस्त की तारीख़ याद रखें।</li>
      <li><strong>नॉमिनी न बनाना</strong> — अनहोनी में परिवार को पैसा निकालने में बहुत परेशानी होती है।</li>
      <li><strong>पात्र न होते हुए जुड़ना</strong> — जैसे आयकर भरने वाले या NPS सदस्य। पकड़े जाने पर जमा पैसा बिना ब्याज लौटेगा।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CHECKLIST -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>CSC जाने से पहले — 5 मिनट की चेकलिस्ट</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>क्या जाँचें</th><th>क्यों</th></tr></thead>
      <tbody>
        <tr><td>आपकी उम्र 18 से 40 के बीच है</td><td>40 के बाद नए पंजीकरण की अनुमति नहीं</td></tr>
        <tr><td>ज़मीन आपके नाम, 2 हेक्टेयर तक</td><td>यही पात्रता की मुख्य शर्त है</td></tr>
        <tr><td>आधार और बैंक खाते में नाम और जन्म तिथि एक जैसी</td><td>मेल न खाने पर पंजीकरण अटकता है</td></tr>
        <tr><td>बैंक खाता चालू है और मोबाइल नंबर जुड़ा है</td><td>किस्त इसी से कटेगी, SMS इसी पर आएगा</td></tr>
        <tr><td>PM किसान की किस्त से अंशदान कटवाना है या नहीं</td><td>यह विकल्प पंजीकरण के समय ही चुनना आसान है</td></tr>
        <tr><td>नॉमिनी का नाम और जन्म तिथि</td><td>फ़ॉर्म में भरनी होगी</td></tr>
      </tbody>
    </table>
  </section>

  <hr class="section-divider" />

  <!-- CONCLUSION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✅</span>
      <h2>निष्कर्ष</h2>
    </div>
    <p>
      तीन बातें याद रखें। पहली, <strong>18 से 40 साल के, 2 हेक्टेयर तक ज़मीन वाले किसान</strong> इस योजना के लिए आवेदन कर सकते हैं, शर्तें पूरी हों तो। दूसरी, <strong>हर महीने ₹55 से ₹200 आप देते हैं और उतना ही सरकार</strong>, और 60 के बाद योजना में ₹3,000 महीना न्यूनतम पेंशन का प्रावधान है। तीसरी, <strong>पंजीकरण CSC पर मुफ़्त है</strong> — और 10 साल से पहले छोड़ने पर सिर्फ़ अपना हिस्सा लौटता है।
    </p>
    <p><strong>जुड़ने से पहले नियम पढ़ें, परिवार से बात करें, और जुड़ें तो किस्त कभी न छूटने दें।</strong></p>
  </section>
"""

FAQS = [
    ("किसान मान-धन योजना में कितनी पेंशन मिलती है?",
     "योजना के नियम में 60 साल की उम्र के बाद <strong>₹3,000 महीना न्यूनतम सुनिश्चित पेंशन</strong> का प्रावधान है। पेंशन मिलते समय किसान की मृत्यु होने पर पति/पत्नी को इसका 50% पारिवारिक पेंशन के रूप में मिलता है।"),
    ("किसान मान-धन योजना में हर महीने कितना पैसा जमा करना होता है?",
     "जुड़ने की उम्र के हिसाब से <strong>₹55 से ₹200 महीना</strong> — 18 साल में ₹55, 29 साल में ₹100 और 40 साल में ₹200। उतनी ही रकम केंद्र सरकार भी अपनी ओर से जमा करती है।"),
    ("किसान मान-धन योजना में कौन आवेदन कर सकता है?",
     "<strong>18 से 40 साल</strong> के छोटे और सीमांत किसान, जिनके नाम 2 हेक्टेयर तक खेती की ज़मीन 1 अगस्त 2019 की स्थिति में भू-अभिलेख में दर्ज हो। आयकर भरने वाले, सरकारी कर्मचारी और NPS/EPFO/ESIC सदस्य इसमें शामिल नहीं हो सकते।"),
    ("किसान मान-धन योजना का पंजीकरण कहाँ होता है?",
     "पंजीकरण नज़दीकी <strong>CSC (जन सेवा केंद्र)</strong> पर होता है और योजना के FAQ के अनुसार यह <strong>मुफ़्त</strong> है। साथ में आधार, बैंक पासबुक और मोबाइल नंबर ले जाएँ; आधिकारिक जानकारी pmkmy.gov.in और maandhan.in पर है।"),
    ("क्या PM किसान की किस्त से मान-धन का पैसा कट सकता है?",
     "हाँ, <strong>PM किसान सम्मान निधि पाने वाले किसान सहमति देकर</strong> अपना मान-धन अंशदान सीधे उसी रकम से कटवा सकते हैं। इसके लिए पंजीकरण के समय ऑटो-डेबिट फ़ॉर्म पर दस्तख़त करने होते हैं।"),
    ("किसान मान-धन योजना बीच में छोड़ दें तो पैसा वापस मिलेगा?",
     "हाँ, पर <strong>सिर्फ़ आपका अपना जमा हिस्सा</strong> ब्याज के साथ लौटता है, सरकार का हिस्सा नहीं। 10 साल से पहले छोड़ने पर बचत खाते का ब्याज मिलता है; 10 साल बाद पर 60 से पहले छोड़ने पर फ़ंड का ब्याज या बचत खाते का ब्याज, जो ज़्यादा हो।"),
    ("किस्त न भरी तो क्या खाता बंद हो जाएगा?",
     "<strong>6 महीने तक किस्त न भरने पर खाता निष्क्रिय (dormant)</strong> हो जाता है, बंद नहीं। बाद में पूरा बकाया ब्याज सहित भरकर उसे फिर चालू कराया जा सकता है; पहले 1 महीने तक कोई लेट-फ़ीस नहीं लगती।"),
    ("क्या पति और पत्नी दोनों को अलग-अलग पेंशन मिल सकती है?",
     "हाँ, <strong>दोनों अलग-अलग पंजीकरण और अलग अंशदान</strong> करें तो दोनों के अलग पेंशन खाते बन सकते हैं, बशर्ते दोनों अपनी-अपनी पात्रता (ज़मीन सहित) पूरी करें। अपनी स्थिति CSC पर पुष्टि कर लें।"),
]

ARTICLE = {
    "slug": "pm-kisan-maandhan-pension",
    "date": "2026-10-02",
    "date_label": "अक्टूबर 2026",
    "read_time": 9,
    "word_count": 2200,
    "lang": "hi",

    "section": "सरकारी योजना",
    "cat_label": "सरकारी योजना",
    "cat_query": "jankari",
    "breadcrumb_leaf": "किसान मान-धन पेंशन",

    "title": "किसान मान-धन योजना: ₹55 से ₹200 महीना, 60 के बाद ₹3,000 पेंशन",
    "description": "18–40 साल के किसान हर महीने ₹55–₹200 जमा करें, उतना ही सरकार जोड़ती है; 60 के बाद ₹3,000 पेंशन का नियम। उम्र-वार तालिका, पात्रता और CSC पंजीकरण।",
    "keywords": "किसान मान-धन योजना, पीएम किसान पेंशन, किसान पेंशन योजना 3000, PM-KMY, kisan maandhan yojana, pm kisan pension yojana, kisan pension 3000 rupaye, pradhan mantri kisan maandhan yojana age chart",

    "og_title": "किसान मान-धन योजना — ₹55 से ₹200 महीना, 60 के बाद ₹3,000 पेंशन | KrashiMitra.in",
    "og_desc": "उम्र-वार अंशदान तालिका, कौन जुड़ सकता है, CSC पर मुफ़्त पंजीकरण और छोड़ने-चूकने के नियम।",

    "hero_image": ("images/articles/pm-kisan-maandhan-pension.webp",
                   "उत्तर भारत के छोटे-छोटे खेत, ऊपर से लिया गया दृश्य",
                   "उत्तर भारत में छोटे-छोटे खेत — यह योजना 2 हेक्टेयर तक ज़मीन वाले किसानों के लिए है।"),

    "headline": "प्रधानमंत्री किसान मान-धन योजना: ₹55 से ₹200 महीना, 60 के बाद ₹3,000 पेंशन",
    "headline_en": "PM Kisan Maandhan Yojana: ₹55–₹200 a month, ₹3,000 pension after 60",
    "schema_desc": "प्रधानमंत्री किसान मान-धन योजना (PM-KMY) — 18 से 40 साल के छोटे-सीमांत किसानों की पेंशन योजना: उम्र-वार अंशदान तालिका, पात्रता, CSC पंजीकरण, ऑटो-डेबिट और छोड़ने के नियम।",
    "schema_keywords": ["किसान मान-धन योजना", "किसान पेंशन योजना", "PM-KMY", "kisan maandhan yojana", "pm kisan pension"],

    "h1": "किसान मान-धन योजना — किसान की पेंशन",
    "h1_en": "Pradhan Mantri Kisan Maandhan Yojana — old-age pension for small farmers",
    "share_title": "किसान मान-धन योजना: ₹55 से ₹200 महीना जमा, 60 के बाद ₹3,000 पेंशन — पूरी तालिका",
    "hero_excerpt": "18 से 40 साल के छोटे किसान हर महीने ₹55 से ₹200 जमा करते हैं और उतना ही सरकार जोड़ती है। जुड़ने से पहले जानें कि किस्त चूकने या बीच में छोड़ने पर क्या होता है।",
    "lede_h2": "किसान मान-धन योजना एक नज़र में",

    "badges": [("badge-disease", "👴 60 के बाद पेंशन"),
               ("badge-season", "🗓️ जुड़ने की उम्र 18–40"),
               ("badge-location", "📍 पूरे भारत में")],

    "quick_facts": [("", "💰", "₹3,000", "60 के बाद महीना पेंशन (नियम)"),
                    ("warn", "🧾", "₹55–₹200", "किसान का मासिक अंशदान"),
                    ("danger", "🌾", "2 हेक्टेयर", "ज़मीन की अधिकतम सीमा")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("wheat", "गेहूं का भाव"), ("mustard", "सरसों का भाव")],

    "card": {
        "emoji": "👴",
        "bg": "#eef6ff",
        "accent": "#1d4ed8",
        "tag": "पेंशन योजना",
        "tag_bg": "#e0ecff",
        "tag_color": "#1d4ed8",
        "title": "किसान मान-धन योजना: ₹55 से ₹200 महीना, 60 के बाद ₹3,000 पेंशन",
        "cats": "jankari",
        "keywords": "kisan maandhan pension yojana pm-kmy 3000 pension csc age chart",
    },

    "related": [
        (f"{SITE}/articles/PM-kisan-samman-nidhi", "#1d4ed8", "💰", "योजना · PM किसान",
         "PM किसान सम्मान निधि — ₹6,000 किस्त का स्टेटस और eKYC"),
        (f"{SITE}/articles/kisan-credit-card", "#1d4ed8", "💳", "योजना · KCC",
         "किसान क्रेडिट कार्ड — ब्याज, सीमा और आवेदन"),
        (f"{SITE}/articles/pm-fasal-bima-yojana-2026", "#1d4ed8", "🛡️", "योजना · फसल बीमा",
         "प्रधानमंत्री फसल बीमा योजना — प्रीमियम और क्लेम"),
        (f"{SITE}/articles/kisan-pehchan-patra-agristack", "#1d4ed8", "🪪", "योजना · Farmer ID",
         "किसान पहचान पत्र (Agristack) — कैसे बनवाएँ"),
        (f"{SITE}/bhav/wheat", "#1b7a3d", "📈", "मंडी · आज के भाव",
         "गेहूं का आज का मंडी भाव — राज्यवार LIVE रेट"),
        (f"{SITE}/chat", "#2e7d32", "🤖", "AI · सहायता",
         "खेती का कोई भी सवाल पूछें — हिंदी में तुरंत जवाब"),
    ],
}
