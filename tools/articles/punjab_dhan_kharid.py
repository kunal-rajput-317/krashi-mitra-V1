# -*- coding: utf-8 -*-
# Punjab paddy procurement, KMS 2026-27. Written 28 Sep 2026.
#
# Sources (every figure below traces to one of these):
#   MSP ₹2,441 / ₹2,461 (+₹72): CCEA, PIB PRID 2260617.
#   Procurement from 1 October 2026: Punjab Mandi Board chairman (Punjabi
#     Jagran); Kisan India (18 purchase centres in Mohali alone; farmers ask
#     for an earlier start because early varieties are ready).
#   anaajkharid.in: "Punjab Anaaj Kharid Portal", Dept. of Food, Civil
#     Supplies & Consumer Affairs; helplines 77430-11156 / 57 / 58 / 59, all
#     working days 9 AM–7 PM — read off the portal on 28 Sep 2026.
#   State procurement agencies for KMS 2026-27: Pungrain, PSWC, Punsup,
#     Markfed — named in the department's own KMS 2026-27 tender notice
#     (foodsuppb.gov.in); FCI alongside.
#   Direct payment into farmers' bank accounts since rabi 2021; farmers
#     registered on the Anaaj Kharid portal with bank account, crop and land
#     details (khasra, plot size); Mandi Board farmer help desks in grain
#     markets: Down To Earth, Punjab govt release (Apr 2021), IDR, Tribune.
#   Quality specs (17% moisture …): FCI uniform specifications.
# Deliberately NOT claimed: a payment deadline in hours (no current Punjab
# directive found), arhtiya commission rates, any quantity cap.
SITE = "https://krashimitra.in"

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>भूमिका</h2>
    </div>
    <p>
      पंजाब में खरीफ विपणन वर्ष 2026-27 की सरकारी धान खरीद <strong>1 अक्टूबर 2026 से</strong> शुरू होनी है, और समर्थन मूल्य <strong>₹2,441 प्रति क्विंटल</strong> है। अगेती किस्मों का धान कई मंडियों में पहले ही आने लगा है, इसलिए किसान संगठन खरीद जल्दी शुरू करने की माँग भी कर रहे हैं।
    </p>
    <p>
      पंजाब का तरीका बाकी राज्यों से थोड़ा अलग है। यहाँ धान मंडी में <strong>आढ़तिये के ज़रिए</strong> बिकता है, पर पैसा आढ़तिये के खाते से नहीं, <strong>सीधे किसान के बैंक खाते में</strong> आता है। और यह तभी होता है जब आपका ब्यौरा — बैंक खाता, ज़मीन और फसल — राज्य के <strong>अनाज खरीद पोर्टल</strong> पर सही दर्ज हो। इस लेख में यही पूरा रास्ता है।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 1 ── -->
  <div class="ad-slot leaderboard" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="3367685932" data-format="auto"></div>
    </div>
  </div>

  <!-- HOW IT WORKS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧾</span>
      <h2>पंजाब में सरकारी धान खरीद कैसे होती है?</h2>
    </div>
    <p>
      धान पंजाब की अनाज मंडियों और खरीद केंद्रों में खरीदा जाता है। खरीद राज्य की एजेंसियाँ करती हैं — <strong>पनग्रेन (Pungrain), पंजाब स्टेट वेयरहाउसिंग कॉर्पोरेशन (PSWC), पनसप (Punsup) और मार्कफेड (Markfed)</strong> — और साथ में भारतीय खाद्य निगम (FCI)। पूरा हिसाब राज्य के खाद्य, नागरिक आपूर्ति एवं उपभोक्ता मामले विभाग के <strong>पंजाब अनाज खरीद पोर्टल (anaajkharid.in)</strong> पर चलता है।
    </p>
    <ul>
      <li><strong>आढ़तिया:</strong> मंडी में आपका धान उतरवाना, सफ़ाई, बोली और तौल — यह काम आढ़तिये के यहाँ होता है।</li>
      <li><strong>खरीद एजेंसी:</strong> समर्थन मूल्य पर धान सरकारी एजेंसी खरीदती है।</li>
      <li><strong>भुगतान:</strong> 2021 से समर्थन मूल्य <strong>सीधे किसान के बैंक खाते में</strong> जाता है, आढ़तिये के खाते से होकर नहीं।</li>
    </ul>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        सीधा भुगतान तभी आता है जब पोर्टल पर <strong>आपका अपना बैंक खाता और ज़मीन का ब्यौरा</strong> दर्ज हो। इसलिए "आढ़तिया सब देख लेगा" मानकर मत बैठिए — एक बार खुद पुष्टि कीजिए कि आपके नाम पर क्या दर्ज है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- MSP TABLE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💰</span>
      <h2>धान का समर्थन मूल्य 2026-27 कितना है?</h2>
    </div>
    <p>
      केंद्रीय मंत्रिमंडल ने खरीफ विपणन वर्ष <strong>2026-27</strong> के लिए धान का समर्थन मूल्य <strong>₹72 प्रति क्विंटल</strong> बढ़ाया है। यही दर पंजाब की हर मंडी में सरकारी खरीद पर लागू होती है।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>श्रेणी</th><th>MSP 2026-27</th><th>पिछला वर्ष</th><th>बढ़ोतरी</th></tr>
      </thead>
      <tbody>
        <tr><td>धान — सामान्य (कॉमन)</td><td><strong>₹2,441 / क्विंटल</strong></td><td>₹2,369</td><td>+₹72</td></tr>
        <tr><td>धान — ग्रेड A</td><td><strong>₹2,461 / क्विंटल</strong></td><td>₹2,389</td><td>+₹72</td></tr>
      </tbody>
    </table>
    <p>
      यानी सामान्य धान <strong>₹24.41 प्रति किलो</strong>। पंजाब में बोई जाने वाली ज़्यादातर परमल किस्में इसी सरकारी खरीद में जाती हैं।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        <strong>बासमती समर्थन मूल्य पर नहीं खरीदा जाता</strong> — वह निजी खरीदारों की खुली बोली पर बिकता है। पंजाब में बासमती का रकबा बड़ा है, इसलिए बेचने से पहले <a href="https://krashimitra.in/bhav/paddy-basmati">बासमती का आज का मंडी भाव</a> और <a href="https://krashimitra.in/bhav/paddy-common">सामान्य धान का भाव</a> दोनों देख लीजिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- COMPARISON -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📊</span>
      <h2>पहले का तरीका बनाम अब का तरीका</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>बिंदु</th><th>✅ अब (सीधा भुगतान)</th><th>❌ पहले (आढ़तिये के ज़रिए)</th></tr>
      </thead>
      <tbody>
        <tr><td>पैसा कहाँ आता है</td><td class="healthy">सीधे किसान के बैंक खाते में</td><td class="diseased">पहले आढ़तिये के खाते में, फिर किसान को</td></tr>
        <tr><td>कटौती का ख़तरा</td><td class="healthy">पुराने उधार की कटौती आढ़तिया खुद नहीं कर सकता</td><td class="diseased">उधार-ब्याज कटकर रकम मिलती थी</td></tr>
        <tr><td>सबूत</td><td class="healthy">पोर्टल पर बिक्री और भुगतान का रिकॉर्ड</td><td class="diseased">आढ़तिये की बही</td></tr>
        <tr><td>शर्त</td><td class="diseased">पोर्टल पर अपना बैंक खाता और ज़मीन दर्ज हो</td><td class="healthy">कोई शर्त नहीं थी</td></tr>
      </tbody>
    </table>
    <p>
      नई व्यवस्था की अकेली "कीमत" यह है कि आपका ब्यौरा पोर्टल पर सही होना चाहिए। एक बार सही हो गया, तो हर सीज़न काम आता है।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- DATES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>2026-27 में खरीद कब से शुरू होगी?</h2>
    </div>
    <p>
      पंजाब मंडी बोर्ड के अनुसार 2026-27 में धान की सरकारी खरीद <strong>1 अक्टूबर 2026</strong> से शुरू होनी है। ज़िलों में खरीद केंद्र तय किए जा रहे हैं — अकेले मोहाली ज़िले में 18 केंद्र बनाए गए हैं। अगेती किस्मों का धान तैयार होने के कारण किसान संगठन इससे पहले खरीद शुरू करने की माँग कर रहे हैं।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>काम</th><th>कब</th></tr>
      </thead>
      <tbody>
        <tr><td>पोर्टल पर अपना ब्यौरा जाँचना</td><td>अभी — खरीद शुरू होने से पहले</td></tr>
        <tr><td>सरकारी खरीद शुरू (घोषित)</td><td><strong>1 अक्टूबर 2026</strong></td></tr>
        <tr><td>कटाई के बाद मंडी ले जाना</td><td>धान सुखाकर, नमी 17% से नीचे होने पर</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        खरीद की तारीख़ सरकार बदल सकती है — पिछले सालों में भी यह आगे-पीछे हुई है। अपनी मंडी की असली तारीख़ मार्केट कमेटी के दफ़्तर से, या अनाज खरीद पोर्टल की हेल्पलाइन <strong>77430-11156, 77430-11157, 77430-11158, 77430-11159</strong> (कार्य दिवस, सुबह 9 से शाम 7) से पुष्टि कर लीजिए।
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

  <!-- DOCUMENTS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📋</span>
      <h2>पोर्टल पर क्या-क्या दर्ज होना चाहिए</h2>
    </div>
    <p>
      सीधा भुगतान पाने के लिए अनाज खरीद पोर्टल पर किसान का ब्यौरा दर्ज होता है। केंद्र सरकार ने सीधे ऑनलाइन भुगतान के लिए <strong>ज़मीन का रिकॉर्ड</strong> भी ज़रूरी किया है, इसलिए ज़मीन की जानकारी अधूरी हो तो भुगतान अटक सकता है।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>ब्यौरा</th><th>किसलिए</th><th>ध्यान रखने की बात</th></tr>
      </thead>
      <tbody>
        <tr><td>आधार और मोबाइल नंबर</td><td>पहचान</td><td>वही नंबर दीजिए जो आपके पास चालू है</td></tr>
        <tr><td>बैंक खाता (खाता संख्या, IFSC)</td><td>भुगतान सीधे इसी में</td><td>खाता <strong>आपके नाम</strong> का और <strong>चालू</strong> हो</td></tr>
        <tr><td>ज़मीन का ब्यौरा (खसरा नंबर, रकबा)</td><td>ज़मीन का रिकॉर्ड</td><td>जमाबंदी की नकल से मिलाकर भरें</td></tr>
        <tr><td>फसल का ब्यौरा</td><td>कितना धान बेचना है</td><td>रकबे के हिसाब से सही मात्रा</td></tr>
        <tr><td>ठेके / बटाई की ज़मीन (यदि लागू)</td><td>ज़मीन किसकी, खेती कौन कर रहा</td><td>मंडी के हेल्प डेस्क से पूछिए कि ब्यौरा कैसे दर्ज होगा; मालिक से लिखित सहमति रखें</td></tr>
      </tbody>
    </table>
    <div class="tip-box tip">
      <span class="tip-icon">🟡</span>
      <div class="tip-content">
        पंजाब मंडी बोर्ड ने अनाज मंडियों में <strong>किसान हेल्प डेस्क</strong> बनाए हैं, जहाँ पोर्टल पर पंजीकरण में मदद मिलती है। पोर्टल पर खुद भी "Farmer Registration" का विकल्प है। जो भी तरीका लें, दर्ज बैंक खाता और ज़मीन का ब्यौरा अपनी आँखों से जाँच लीजिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- AT THE MANDI -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">⚖️</span>
      <h2>मंडी में क्या-क्या होता है</h2>
    </div>
    <ol>
      <li><strong>ढेरी और सफ़ाई:</strong> धान आढ़तिये के फड़ पर उतरता है, जहाँ सफ़ाई होती है।</li>
      <li><strong>नमी और गुणवत्ता की जाँच:</strong> खरीद एजेंसी का निरीक्षक नमी और दानों की गुणवत्ता देखता है।</li>
      <li><strong>खरीद और तौल:</strong> समर्थन मूल्य पर एजेंसी की खरीद और तौल होती है।</li>
      <li><strong>J-फॉर्म:</strong> बिक्री के बाद J-फॉर्म बनता है — यह आपकी बिक्री की पर्ची है। इसकी प्रति आढ़तिये से ज़रूर लीजिए।</li>
      <li><strong>भुगतान:</strong> बिक्री के रिकॉर्ड के आधार पर पैसा सीधे आपके खाते में आता है।</li>
    </ol>
    <table class="article-table">
      <thead>
        <tr><th>पैमाना</th><th>अधिकतम सीमा</th><th>इसका मतलब</th></tr>
      </thead>
      <tbody>
        <tr><td>नमी</td><td><strong>17.0%</strong></td><td>इससे ज़्यादा पर खरीद नहीं होती</td></tr>
        <tr><td>अकार्बनिक अपद्रव्य</td><td>1.0%</td><td>मिट्टी, कंकड़, धूल</td></tr>
        <tr><td>कार्बनिक अपद्रव्य</td><td>1.0%</td><td>पुआल, डंठल, खरपतवार के बीज</td></tr>
        <tr><td>क्षतिग्रस्त, विवर्णित, अंकुरित व घुन लगे दाने</td><td>5.0%</td><td>बारिश में भीगा या ढेर में गरम हुआ धान</td></tr>
        <tr><td>अपरिपक्व, सिकुड़े व झुर्रीदार दाने</td><td>3.0%</td><td>जल्दी काटी फसल</td></tr>
      </tbody>
    </table>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        कंबाइन से सुबह-सुबह ओस में कटे धान में नमी सबसे ज़्यादा होती है। दिन चढ़ने पर कटाई कीजिए और मंडी में फैलाकर सुखाइए — पूरा तरीका <a href="https://krashimitra.in/articles/dhan-nami-mandi-rejection">धान में नमी 17% का पूरा नियम</a> में है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- PAYMENT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏦</span>
      <h2>भुगतान कैसे और कहाँ आता है?</h2>
    </div>
    <p>
      2021 से पंजाब में समर्थन मूल्य <strong>सीधे किसान के बैंक खाते में</strong> ऑनलाइन भेजा जाता है। भुगतान उसी खाते में जाता है जो अनाज खरीद पोर्टल पर आपके नाम से दर्ज है।
    </p>
    <ul>
      <li><strong>खाता चालू हो:</strong> निष्क्रिय खाते में भुगतान लौट आता है।</li>
      <li><strong>नाम एक जैसा हो:</strong> पोर्टल, बैंक और आधार में नाम की वर्तनी अलग हो तो भुगतान अटक सकता है।</li>
      <li><strong>ज़मीन का रिकॉर्ड पूरा हो:</strong> ज़मीन का ब्यौरा अधूरा होने पर ऑनलाइन भुगतान रुक सकता है।</li>
      <li><strong>देर होने पर:</strong> J-फॉर्म लेकर मार्केट कमेटी दफ़्तर जाइए, या पोर्टल की हेल्पलाइन 77430-11156 / 57 / 58 / 59 पर बात कीजिए।</li>
    </ul>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        पुराने उधार के बदले "पैसा मेरे खाते में मँगवा लो" जैसी कोई भी बात मत मानिए। सरकारी खरीद का भुगतान आपके अपने खाते में आना चाहिए — उधार का हिसाब अलग से, लिखित में कीजिए।
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
      <li><strong>पोर्टल पर दर्ज बैंक खाता जाँचे बिना मंडी जाना</strong> — गलत खाता मतलब गलत जगह पैसा।</li>
      <li><strong>ज़मीन का ब्यौरा अधूरा छोड़ना</strong> — सीधे भुगतान के लिए ज़मीन का रिकॉर्ड ज़रूरी है।</li>
      <li><strong>ओस में भीगा या कच्चा धान काटकर लाना</strong> — 17% से ज़्यादा नमी पर खरीद नहीं होती और मंडी में दिनों इंतज़ार होता है।</li>
      <li><strong>बिना सफ़ाई का धान लाना</strong> — पुआल-मिट्टी की सीमा 1%-1% है।</li>
      <li><strong>J-फॉर्म की प्रति न लेना</strong> — बाद में हर शिकायत इसी पर टिकती है।</li>
      <li><strong>बासमती को MSP वाली खरीद में मानकर चलना</strong> — बासमती खुली बोली पर बिकता है।</li>
      <li><strong>पराली जलाना</strong> — खेत की उपजाऊ ताक़त जलती है; इसके बजाय <a href="https://krashimitra.in/articles/parali-prabandhan">पराली प्रबंधन के तरीके</a> देखिए।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CALENDAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>कब क्या करें — पूरा क्रम</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>समय</th><th>ज़रूरी काम</th></tr></thead>
      <tbody>
        <tr><td>खरीद से पहले (सितंबर)</td><td>पोर्टल पर बैंक खाता, ज़मीन और फसल का ब्यौरा जाँचना</td></tr>
        <tr><td>कटाई</td><td>दाने पकने पर, ओस सूखने के बाद कटाई</td></tr>
        <tr><td>मंडी ले जाने से पहले</td><td>सुखाई और सफ़ाई; नमी 17% से नीचे</td></tr>
        <tr><td>मंडी में</td><td>सफ़ाई, जाँच, खरीद और तौल; J-फॉर्म की प्रति लेना</td></tr>
        <tr><td>बिक्री के कुछ दिन बाद</td><td>बैंक खाते में भुगतान देखना; न आए तो शिकायत</td></tr>
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
      पंजाब में धान बेचना आज भी आढ़तिये के फड़ से होता है, पर पैसा अब सीधे आपके पास आता है — बशर्ते <strong>अनाज खरीद पोर्टल पर आपका बैंक खाता और ज़मीन का ब्यौरा सही हो</strong>। खरीद शुरू होने से पहले यही एक जाँच कर लीजिए, धान 17% नमी से नीचे सुखाकर लाइए, और J-फॉर्म सँभालकर रखिए।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        यह लेख सामान्य जानकारी के लिए है। समर्थन मूल्य, खरीद की तारीख़ और नियम सरकार के आदेशों से तय होते हैं और बदलते रहते हैं। KrashiMitra न सरकारी एजेंट है, न आढ़तिया, न किसी की फसल खरीदता या बिकवाता है — अंतिम पुष्टि हमेशा <strong>anaajkharid.in</strong>, अपनी मार्केट कमेटी या हेल्पलाइन से ही कीजिए।
      </div>
    </div>
  </section>
"""

FAQS = [
    ("पंजाब में धान की खरीद 2026 में कब से शुरू होगी?",
     "पंजाब मंडी बोर्ड के अनुसार खरीफ विपणन वर्ष 2026-27 में धान की सरकारी खरीद <strong>1 अक्टूबर 2026</strong> से शुरू होनी है। तारीख़ सरकार बदल सकती है, इसलिए अपनी मंडी की स्थिति मार्केट कमेटी से पुष्टि कर लीजिए।"),
    ("पंजाब में धान का MSP 2026-27 कितना है?",
     "खरीफ विपणन वर्ष 2026-27 में धान का समर्थन मूल्य <strong>सामान्य ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल</strong> है, जो पिछले साल से ₹72 अधिक है। बासमती धान समर्थन मूल्य पर नहीं खरीदा जाता।"),
    ("क्या धान का पैसा आढ़तिये के खाते में आता है?",
     "नहीं — 2021 से पंजाब में समर्थन मूल्य <strong>सीधे किसान के अपने बैंक खाते में</strong> भेजा जाता है। इसके लिए अनाज खरीद पोर्टल पर आपका बैंक खाता और ज़मीन का ब्यौरा आपके नाम से सही दर्ज होना चाहिए।"),
    ("अनाज खरीद पोर्टल क्या है?",
     "अनाज खरीद पोर्टल (<strong>anaajkharid.in</strong>) पंजाब के खाद्य, नागरिक आपूर्ति एवं उपभोक्ता मामले विभाग की ऑनलाइन व्यवस्था है, जिस पर खरीद और भुगतान का हिसाब चलता है। इसकी हेल्पलाइन 77430-11156, 77430-11157, 77430-11158 और 77430-11159 है।"),
    ("पंजाब में धान कौन-सी एजेंसियाँ खरीदती हैं?",
     "धान <strong>पनग्रेन, पंजाब स्टेट वेयरहाउसिंग कॉर्पोरेशन, पनसप और मार्कफेड</strong> जैसी राज्य एजेंसियाँ और भारतीय खाद्य निगम (FCI) खरीदते हैं। किसान के लिए प्रक्रिया एक जैसी है — मंडी में आढ़तिये के फड़ पर बिक्री और सीधा भुगतान।"),
    ("J-फॉर्म क्या है और यह क्यों ज़रूरी है?",
     "J-फॉर्म <strong>मंडी में फसल बिकने की पर्ची</strong> है, जिसमें मात्रा, भाव और रकम दर्ज होती है। भुगतान अटकने या कोई शिकायत करने पर यही सबसे बड़ा सबूत है, इसलिए इसकी प्रति आढ़तिये से ज़रूर लीजिए।"),
    ("धान में कितनी नमी चलती है?",
     "सरकारी खरीद में धान की अधिकतम नमी <strong>17%</strong> है। इसके अलावा अकार्बनिक और कार्बनिक अपद्रव्य 1%-1%, क्षतिग्रस्त दाने 5% और अपरिपक्व दाने 3% तक ही मान्य हैं।"),
]

ARTICLE = {
    "slug": "punjab-dhan-kharid",
    "date": "2026-09-28",
    "date_label": "सितंबर 2026",
    "read_time": 8,
    "word_count": 1900,
    "lang": "hi",

    "section": "सरकारी योजना",
    "cat_label": "सरकारी योजना",
    "cat_query": "jankari",
    "breadcrumb_leaf": "पंजाब धान खरीद",

    "title": "पंजाब धान खरीद 2026-27: 1 अक्टूबर से, MSP ₹2,441, सीधा भुगतान",
    "description": "पंजाब में धान की सरकारी खरीद 1 अक्टूबर 2026 से। MSP ₹2,441, अनाज खरीद पोर्टल पर क्या दर्ज हो, J-फॉर्म, नमी 17% और सीधा भुगतान — पूरी जानकारी।",
    "keywords": "पंजाब धान खरीद 2026, punjab dhan kharid, punjab paddy procurement 2026, anaaj kharid portal, anaajkharid.in, अनाज खरीद पोर्टल, धान MSP 2441, punjab mandi paddy 1 october, j form punjab, ਝੋਨੇ ਦੀ ਖਰੀਦ",

    "og_title": "पंजाब धान खरीद 2026-27: 1 अक्टूबर से, MSP ₹2,441, सीधा भुगतान",
    "og_desc": "पंजाब में धान की सरकारी खरीद 1 अक्टूबर 2026 से। अनाज खरीद पोर्टल, J-फॉर्म, नमी 17% और सीधा भुगतान — पूरी जानकारी।",
    "hero_image": ("images/articles/punjab-dhan-kharid.webp",
                   "पंजाब के गुरदासपुर ज़िले में बटाला के पास धान के खेत",
                   "पंजाब के बटाला (गुरदासपुर) के धान के खेत — यही फसल मंडी में समर्थन मूल्य पर बिकती है। (मंडी की कोई स्वतंत्र-लाइसेंस वाली तस्वीर उपलब्ध नहीं है।)"),
    "headline": "पंजाब धान खरीद 2026-27 — अनाज खरीद पोर्टल, मंडी और सीधा भुगतान",
    "headline_en": "Punjab Paddy Procurement 2026-27 — Anaaj Kharid Portal, Mandi &amp; Direct Payment",
    "schema_desc": "पंजाब में समर्थन मूल्य पर धान बेचने की पूरी प्रक्रिया: 1 अक्टूबर 2026 से खरीद, अनाज खरीद पोर्टल पर बैंक खाता व ज़मीन का ब्यौरा, खरीद एजेंसियाँ, J-फॉर्म, नमी व गुणवत्ता मानक और सीधा भुगतान।",
    "schema_keywords": ["पंजाब धान खरीद", "Punjab paddy procurement", "Anaaj Kharid", "MSP",
                        "समर्थन मूल्य", "J-form", "पंजाब"],

    "h1": "पंजाब धान खरीद 2026-27",
    "h1_en": "Selling Paddy at MSP in Punjab — Portal, Mandi &amp; Direct Payment",
    "share_title": "पंजाब धान खरीद 2026-27 — 1 अक्टूबर से, MSP ₹2,441, भुगतान सीधे खाते में",
    "hero_excerpt": "बिक्री आढ़तिये के फड़ पर, पैसा सीधे आपके खाते में — पर तभी, जब अनाज खरीद पोर्टल पर आपका ब्यौरा सही हो।",
    "lede_h2": "आढ़तिये का फड़, पर पैसा आपका अपना",

    "badges": [("badge-location", "📍 पंजाब"),
               ("badge-season", "🗓️ अक्टूबर – नवंबर"),
               ("badge-disease", "🏦 भुगतान सीधे खाते में")],

    "quick_facts": [("", "💰", "₹2,441", "सामान्य धान का MSP, प्रति क्विंटल"),
                    ("warn", "📅", "1 अक्टूबर", "2026-27 में खरीद शुरू (घोषित)"),
                    ("danger", "💧", "17%", "इससे ऊपर नमी तो खरीद नहीं")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-common", "धान का भाव"),
                   ("paddy-basmati", "बासमती धान का भाव"),
                   ("wheat", "गेहूं का भाव"),
                   ("maize", "मक्का का भाव")],

    "card": {
        "emoji": "🧾", "bg": "#eff6ff", "accent": "#0369a1",
        "tag": "पंजाब धान खरीद", "tag_bg": "#dbeafe", "tag_color": "#0369a1",
        "title": "पंजाब धान खरीद 2026-27 — अनाज खरीद पोर्टल, मंडी और सीधा भुगतान",
        "cats": "jankari",
        "keywords": "पंजाब धान खरीद punjab dhan kharid paddy procurement anaaj kharid portal j form MSP 2441 नमी 17% सीधा भुगतान मंडी आढ़तिया",
    },

    "related": [
        (f"{SITE}/articles/haryana-dhan-kharid", "#0369a1", "🧾", "हरियाणा · धान खरीद",
         "हरियाणा धान खरीद 2026-27 — मेरी फसल मेरा ब्यौरा से मंडी तक"),
        (f"{SITE}/articles/up-dhan-kharid-panjikaran", "#0369a1", "🧾", "UP · धान खरीद",
         "UP धान खरीद पंजीकरण — MSP ₹2,441 पर धान बेचने की पूरी प्रक्रिया"),
        (f"{SITE}/articles/dhan-nami-mandi-rejection", "#0f766e", "💧", "धान · गुणवत्ता",
         "धान में नमी कितनी होनी चाहिए? 17% का पूरा नियम"),
        (f"{SITE}/articles/parali-prabandhan", "#a16207", "🔥", "पराली · प्रबंधन",
         "पराली प्रबंधन — जलाए बिना पुआल का सही इस्तेमाल"),
        (f"{SITE}/articles/enam-online-fasal-bechna", "#7c3aed", "🛒", "मंडी · ऑनलाइन",
         "e-NAM से ऑनलाइन फसल बेचना — पूरी प्रक्रिया"),
        (f"{SITE}/bhav/paddy-common", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "धान का आज का मंडी भाव — राज्यवार LIVE रेट"),
    ],
}
