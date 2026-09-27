# -*- coding: utf-8 -*-
# Haryana paddy procurement, KMS 2026-27. Written 28 Sep 2026.
#
# Sources (every figure below traces to one of these):
#   MSP ₹2,441 / ₹2,461 (+₹72): CCEA, PIB PRID 2260617.
#   fasal.haryana.gov.in (Meri Fasal Mera Byora): helpline 1800 180 2117,
#     Kisan Call Center 1800 180 2060 (Mon–Fri 9–5); Kharif 2026 deadline
#     31.07.2026 — read off the portal on 28 Sep 2026.
#   Portal reopened 21–27 Sep 2026; records checked by satellite data,
#     ground-truthing and physical verification: UNI India.
#   Weighing from 24 Sep, gate passes from 25 Sep 2026 after the Kurukshetra
#     farmers' dharna was called off: ETV Bharat, 23 Sep 2026. 249 mandis.
#   ekharid.haryana.gov.in: Food & Civil Supplies Dept, toll-free 1800-180-2060.
#   eKharid Haryana app shows J-form and MSP payment status: Play Store listing.
#   Payment within 72 hours of the J-form: Chief Secretary's direction, The
#     Tribune. Direct payment to farmers since 2021: Down To Earth, ThePrint.
#   MFMB documents (PPP family ID, Aadhaar + OTP, jamabandi/fard with
#     khasra-khewat, bank account): multiple state-news guides, consistent.
#   Quality specs (17% moisture …): FCI uniform specifications, as in
#     up_dhan_kharid_panjikaran.
# Deliberately NOT claimed: agency-by-agency split, any per-acre quantity cap,
# any interest on late payment — none could be sourced cleanly for 2026-27.
SITE = "https://krashimitra.in"

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>भूमिका</h2>
    </div>
    <p>
      हरियाणा की मंडियों में इस बार धान की सरकारी खरीद <strong>24 सितंबर 2026 से तुलाई</strong> और <strong>25 सितंबर से गेट पास</strong> के साथ शुरू हुई। समर्थन मूल्य <strong>₹2,441 प्रति क्विंटल</strong> है। पर इस भाव पर धान तभी बिकता है जब एक शर्त पूरी हो: आपकी फसल <strong>"मेरी फसल मेरा ब्यौरा" पोर्टल पर दर्ज</strong> हो।
    </p>
    <p>
      हर साल मंडी के गेट पर यहीं झगड़ा होता है। किसान ट्रॉली लेकर पहुँचता है, और पता चलता है कि पोर्टल पर धान दर्ज ही नहीं है, या रकबा कम दर्ज है, या बैंक खाता गलत है। इस लेख में पूरा रास्ता एक जगह है: पंजीकरण कैसे करें, कौन-से कागज़ लगते हैं, मंडी में गेट पास और J-फॉर्म क्या है, नमी कितनी चलती है, और पैसा कितने दिन में आता है।
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
      <h2>हरियाणा में सरकारी धान खरीद कैसे होती है?</h2>
    </div>
    <p>
      हरियाणा में धान <strong>अनाज मंडियों</strong> में खरीदा जाता है — इस सीज़न के लिए प्रदेश की <strong>249 मंडियाँ</strong> तैयार की गईं। पूरी खरीद राज्य के खाद्य, नागरिक आपूर्ति विभाग की <strong>ई-खरीद (e-Kharid)</strong> व्यवस्था से चलती है: मंडी के गेट पर गेट पास, तौल, बिक्री की पर्ची यानी <strong>J-फॉर्म</strong>, और फिर भुगतान — सब इसी सिस्टम में दर्ज होता है।
    </p>
    <p>
      ई-खरीद उसी किसान का धान उठाती है जिसकी फसल <strong>मेरी फसल मेरा ब्यौरा (MFMB)</strong> पोर्टल पर दर्ज है। यानी MFMB पर पंजीकरण पहला दरवाज़ा है, और ई-खरीद उसके बाद का पूरा रास्ता।
    </p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        मंडी में आढ़तिया आज भी बिक्री कराता है, पर <strong>पैसा आढ़तिये के खाते से होकर नहीं आता</strong> — 2021 से समर्थन मूल्य सीधे किसान के बैंक खाते में भेजा जाता है। इसलिए पंजीकरण में दर्ज बैंक खाता ही सबसे ज़रूरी कड़ी है।
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
      खरीफ विपणन वर्ष <strong>2026-27</strong> के लिए केंद्रीय मंत्रिमंडल ने धान का समर्थन मूल्य <strong>₹72 प्रति क्विंटल</strong> बढ़ाया है। यही दर हरियाणा की हर मंडी में सरकारी खरीद पर लागू होती है।
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
      एक क्विंटल = 100 किलो, यानी सामान्य धान <strong>₹24.41 प्रति किलो</strong>। ग्रेड A और कॉमन का फ़र्क दाने की बनावट और किस्म से तय होता है, और मंडी में खरीद करने वाला कर्मचारी ही श्रेणी दर्ज करता है।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        <strong>बासमती धान समर्थन मूल्य पर नहीं खरीदा जाता</strong> — वह खुली बोली पर बिकता है, और अक्सर MSP से ऊँचे भाव पर। बेचने से पहले <a href="https://krashimitra.in/bhav/paddy-basmati">बासमती का आज का मंडी भाव</a> और <a href="https://krashimitra.in/bhav/paddy-common">सामान्य धान का भाव</a> दोनों देख लीजिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- COMPARISON -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📊</span>
      <h2>पोर्टल पर दर्ज फसल बनाम बिना पंजीकरण — फ़र्क कहाँ पड़ता है</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>बिंदु</th><th>✅ MFMB पर दर्ज फसल</th><th>❌ पोर्टल पर दर्ज नहीं</th></tr>
      </thead>
      <tbody>
        <tr><td>भाव</td><td class="healthy">₹2,441 समर्थन मूल्य पर सरकारी खरीद</td><td class="diseased">सिर्फ़ निजी खरीदार; अक्सर MSP से कम</td></tr>
        <tr><td>गेट पास</td><td class="healthy">ई-खरीद से कटता है</td><td class="diseased">सरकारी खरीद का गेट पास नहीं कटता</td></tr>
        <tr><td>तौल व पर्ची</td><td class="healthy">दर्ज तौल, J-फॉर्म</td><td class="diseased">जैसा खरीदार करे, कई बार बिना पर्ची</td></tr>
        <tr><td>भुगतान</td><td class="healthy">सीधे आपके बैंक खाते में</td><td class="diseased">नकद या उधार, खरीदार की शर्त पर</td></tr>
        <tr><td>सबूत</td><td class="healthy">J-फॉर्म, ऐप पर भुगतान की स्थिति</td><td class="diseased">कुछ लिखित नहीं</td></tr>
        <tr><td>शर्त</td><td class="diseased">समय पर पंजीकरण, नमी 17% तक</td><td class="healthy">कोई शर्त नहीं</td></tr>
      </tbody>
    </table>
    <p>
      आख़िरी पंक्ति जानबूझकर उलटी है। सरकारी खरीद की शर्तें असली हैं — पर वे बस <strong>समय पर पंजीकरण और सूखा धान</strong> माँगती हैं, और बदले में तय भाव और लिखित सबूत देती हैं।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- DATES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>2026 की ज़रूरी तारीख़ें</h2>
    </div>
    <p>
      खरीफ 2026 के लिए MFMB पर पंजीकरण की अंतिम तारीख <strong>31 जुलाई 2026</strong> थी। जो किसान चूक गए, उनके लिए सरकार ने पोर्टल <strong>21 से 27 सितंबर 2026</strong> तक दोबारा खोला। मंडियों में खरीद के लिए किसान संगठनों और प्रशासन के बीच सहमति के बाद तुलाई और गेट पास की तारीख़ें तय हुईं।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>काम</th><th>तारीख़ (2026)</th></tr>
      </thead>
      <tbody>
        <tr><td>MFMB पर खरीफ पंजीकरण की अंतिम तिथि</td><td>31 जुलाई</td></tr>
        <tr><td>छूटे किसानों के लिए पोर्टल दोबारा खुला</td><td><strong>21 – 27 सितंबर</strong></td></tr>
        <tr><td>मंडियों में धान की तुलाई शुरू</td><td><strong>24 सितंबर</strong></td></tr>
        <tr><td>ई-खरीद पर गेट पास कटना शुरू</td><td><strong>25 सितंबर</strong></td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        तारीख़ें सरकार के आदेश से तय होती हैं और बदल सकती हैं — पोर्टल दोबारा खुलेगा या नहीं, यह भी हर बार अलग फ़ैसला होता है। अपनी मंडी की असली स्थिति <strong>fasal.haryana.gov.in</strong>, मार्केट कमेटी के दफ़्तर, या MFMB हेल्पलाइन <strong>1800 180 2117</strong> से पुष्टि कर लीजिए।
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
      <h2>मेरी फसल मेरा ब्यौरा — कौन-से कागज़ चाहिए</h2>
    </div>
    <p>
      पंजीकरण से पहले ये सब एक जगह रख लीजिए। सबसे ज़्यादा समय ज़मीन का खसरा-खेवट नंबर खोजने में जाता है, इसलिए फर्द या जमाबंदी की नकल पहले निकलवा लीजिए।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>दस्तावेज़</th><th>किसलिए</th><th>ध्यान रखने की बात</th></tr>
      </thead>
      <tbody>
        <tr><td>परिवार पहचान पत्र (फैमिली ID / PPP)</td><td>हरियाणा में किसान की पहचान</td><td>परिवार पहचान पत्र का ब्यौरा अपडेट हो</td></tr>
        <tr><td>आधार कार्ड और उससे जुड़ा मोबाइल</td><td>पहचान और OTP</td><td>OTP उसी नंबर पर आता है जो आधार से जुड़ा है</td></tr>
        <tr><td>जमाबंदी / फर्द की नकल</td><td>ज़मीन का ब्यौरा</td><td>खसरा और खेवट नंबर दोनों चाहिए</td></tr>
        <tr><td>बैंक खाता (खाता संख्या, IFSC)</td><td>भुगतान इसी खाते में</td><td>खाता <strong>चालू</strong> हो और आपके ही नाम पर हो</td></tr>
        <tr><td>फसल का ब्यौरा</td><td>किस खेत में कौन-सी फसल</td><td>धान का रकबा सही भरें — सत्यापन में यही जाँचा जाता है</td></tr>
      </tbody>
    </table>
    <div class="tip-box tip">
      <span class="tip-icon">🟡</span>
      <div class="tip-content">
        पोर्टल पर दर्ज फसल की जाँच <strong>सैटेलाइट डेटा, मौके की जाँच और भौतिक सत्यापन</strong> से होती है। जो बोया है वही और उतना ही दर्ज कीजिए — ज़्यादा रकबा लिखने पर पूरा पंजीकरण अटक सकता है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- HOW TO REGISTER -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💻</span>
      <h2>पंजीकरण कैसे करें — क्रम से</h2>
    </div>
    <p>
      पंजीकरण <strong>fasal.haryana.gov.in</strong> पर होता है। यह काम आप खुद मोबाइल से कर सकते हैं, या नज़दीकी <strong>अटल सेवा केंद्र / कॉमन सर्विस सेंटर (CSC)</strong> पर करा सकते हैं।
    </p>
    <ol>
      <li><strong>पोर्टल खोलिए:</strong> fasal.haryana.gov.in पर किसान पंजीकरण वाला विकल्प चुनिए।</li>
      <li><strong>पहचान दर्ज कीजिए:</strong> परिवार पहचान पत्र / आधार का ब्यौरा भरकर मोबाइल पर आया OTP डालिए।</li>
      <li><strong>ज़मीन का ब्यौरा:</strong> ज़िला, तहसील, गाँव, खसरा और खेवट नंबर — जमाबंदी की नकल सामने रखकर।</li>
      <li><strong>फसल का ब्यौरा:</strong> किस खसरे में धान है और कितने रकबे में — सही-सही।</li>
      <li><strong>बैंक खाता:</strong> खाता संख्या और IFSC। अपने नाम का चालू खाता ही दीजिए।</li>
      <li><strong>जमा करके रसीद सँभालिए:</strong> पंजीकरण की रसीद या प्रिंट पूरे सीज़न अपने पास रखिए।</li>
    </ol>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        पोर्टल के पन्ने और विकल्पों के नाम हर सीज़न में बदल सकते हैं। अटकें तो MFMB हेल्पलाइन <strong>1800 180 2117</strong> या किसान कॉल सेंटर <strong>1800 180 2060</strong> पर (सोमवार से शुक्रवार, सुबह 9 से शाम 5) बात कीजिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- FREE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🆓</span>
      <h2>पंजीकरण के पैसे किसी को मत दीजिए</h2>
    </div>
    <p>
      MFMB पर पंजीकरण <strong>सरकार की ओर से निःशुल्क</strong> है। सेवा केंद्र अपनी टाइपिंग-प्रिंट की मामूली फ़ीस ले सकते हैं, पर "पक्का पंजीकरण", "जल्दी गेट पास" या "सत्यापन पास कराने" के नाम पर पैसे माँगना वसूली है।
    </p>
    <ul>
      <li><strong>OTP किसी को न बताइए:</strong> OTP से ही आपका पंजीकरण और बैंक खाता जुड़ता है।</li>
      <li><strong>बैंक खाता खुद भरिए या खुद जाँचिए:</strong> किसी दूसरे का खाता दर्ज हो गया तो आपकी फसल का पैसा उसी में जाएगा।</li>
      <li><strong>रसीद ज़रूर लीजिए:</strong> सेवा केंद्र से कराया हो तो प्रिंट लिए बिना मत लौटिए।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- AT THE MANDI -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">⚖️</span>
      <h2>मंडी में क्या-क्या होता है — गेट पास से J-फॉर्म तक</h2>
    </div>
    <ol>
      <li><strong>गेट पास:</strong> मंडी के गेट पर आपकी MFMB एंट्री से ई-खरीद पर गेट पास कटता है। यही आपकी ट्रॉली का सरकारी रिकॉर्ड है।</li>
      <li><strong>नमी और गुणवत्ता की जाँच:</strong> ढेरी से नमूना लेकर नमी और दानों की गुणवत्ता जाँची जाती है।</li>
      <li><strong>खरीद और तौल:</strong> समर्थन मूल्य पर खरीद होती है और तौल दर्ज की जाती है।</li>
      <li><strong>J-फॉर्म:</strong> बिक्री के बाद J-फॉर्म बनता है — इसमें मात्रा, भाव और रकम दर्ज होती है। भुगतान इसी के आधार पर होता है।</li>
    </ol>
    <table class="article-table">
      <thead>
        <tr><th>पैमाना</th><th>अधिकतम सीमा</th><th>इसका मतलब</th></tr>
      </thead>
      <tbody>
        <tr><td>नमी</td><td><strong>17.0%</strong></td><td>सबसे आम कारण जिससे धान नहीं बिकता</td></tr>
        <tr><td>अकार्बनिक अपद्रव्य</td><td>1.0%</td><td>मिट्टी, कंकड़, धूल</td></tr>
        <tr><td>कार्बनिक अपद्रव्य</td><td>1.0%</td><td>पुआल, डंठल, खरपतवार के बीज</td></tr>
        <tr><td>क्षतिग्रस्त, विवर्णित, अंकुरित व घुन लगे दाने</td><td>5.0%</td><td>बारिश में भीगा या ढेर में गरम हुआ धान</td></tr>
        <tr><td>अपरिपक्व, सिकुड़े व झुर्रीदार दाने</td><td>3.0%</td><td>जल्दी काटी या कमज़ोर बढ़वार वाली फसल</td></tr>
      </tbody>
    </table>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        कंबाइन से कटे धान में नमी अक्सर ज़्यादा रहती है। मंडी लाने से पहले धूप में फैलाकर सुखाइए — नमी घटाने का पूरा तरीका <a href="https://krashimitra.in/articles/dhan-nami-mandi-rejection">धान में नमी 17% का पूरा नियम</a> में दिया है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- PAYMENT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏦</span>
      <h2>पैसा कितने दिन में आता है?</h2>
    </div>
    <p>
      भुगतान <strong>सीधे आपके बैंक खाते में</strong> भेजा जाता है — वही खाता जो पंजीकरण में दर्ज है। हरियाणा के मुख्य सचिव ने निर्देश दिया है कि किसान को <strong>J-फॉर्म कटने के 72 घंटे के भीतर</strong> भुगतान मिले। यह शासन का निर्देश है; व्यवहार में कभी-कभी कुछ दिन ज़्यादा लग सकते हैं।
    </p>
    <ul>
      <li><strong>स्थिति खुद देखिए:</strong> <strong>eKharid Haryana</strong> मोबाइल ऐप पर बेचे गए धान का J-फॉर्म और भुगतान की स्थिति देखी जा सकती है।</li>
      <li><strong>खाता चालू हो:</strong> बंद या निष्क्रिय खाते में भुगतान लौट आता है।</li>
      <li><strong>नाम मेल खाए:</strong> पंजीकरण, बैंक खाते और परिवार पहचान पत्र में नाम की वर्तनी अलग हो तो भुगतान अटक सकता है।</li>
      <li><strong>देर होने पर:</strong> J-फॉर्म की प्रति लेकर मार्केट कमेटी दफ़्तर जाइए, या ई-खरीद की टोल-फ्री हेल्पलाइन <strong>1800-180-2060</strong> पर शिकायत कीजिए।</li>
    </ul>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        सरकारी खरीद का पैसा नकद नहीं दिया जाता। कोई "आपका धान अपने नाम पर बिकवा देता हूँ" कहे, तो मना कीजिए — आपकी फसल, आपका पंजीकरण और आपका खाता, तीनों एक ही होने चाहिए।
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
      <li><strong>पंजीकरण की तारीख़ निकल जाने देना</strong> — पोर्टल दोबारा खुलेगा, इसकी कोई गारंटी नहीं होती।</li>
      <li><strong>धान का रकबा बढ़ाकर लिखना</strong> — सैटेलाइट और मौके की जाँच में पकड़ा जाता है और पूरा पंजीकरण अटकता है।</li>
      <li><strong>किसी और का बैंक खाता दर्ज करवा देना</strong> — भुगतान उसी खाते में जाता है जो पोर्टल पर है।</li>
      <li><strong>गीला धान लेकर मंडी पहुँचना</strong> — 17% से ज़्यादा नमी पर धान बिकता नहीं, और मंडी में इंतज़ार लंबा होता है।</li>
      <li><strong>बिना साफ़ किए धान लाना</strong> — पुआल-मिट्टी की सीमा 1%-1% है।</li>
      <li><strong>J-फॉर्म लिए बिना लौट आना</strong> — भुगतान और शिकायत, दोनों इसी पर टिकते हैं।</li>
      <li><strong>बासमती को MSP की लाइन में लगाना</strong> — बासमती खुली बोली पर बिकता है; उसका भाव अलग देखिए।</li>
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
        <tr><td>बुवाई के बाद (जुलाई तक)</td><td>MFMB पर धान का रकबा दर्ज करना; बैंक खाते की जाँच</td></tr>
        <tr><td>कटाई से पहले</td><td>पंजीकरण की स्थिति देखना; मंडी और खरीद शुरू होने की तारीख़ पता करना</td></tr>
        <tr><td>कटाई के बाद</td><td>धूप में सुखाना और साफ़ करना — नमी 17% से नीचे लाना</td></tr>
        <tr><td>मंडी में</td><td>गेट पास, नमी की जाँच, खरीद और तौल, J-फॉर्म लेना</td></tr>
        <tr><td>बिक्री के 3 दिन बाद</td><td>eKharid Haryana ऐप या बैंक में भुगतान देखना; न आए तो शिकायत</td></tr>
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
      हरियाणा में समर्थन मूल्य का रास्ता तीन कड़ियों से बनता है: <strong>मेरी फसल मेरा ब्यौरा पर सही पंजीकरण</strong>, <strong>मंडी में गेट पास और J-फॉर्म</strong>, और <strong>आपके नाम का चालू बैंक खाता</strong>। इनमें से एक भी कड़ी टूटी तो धान या तो बिकता नहीं, या उसका पैसा अटक जाता है।
    </p>
    <p>
      धान को 17% नमी से नीचे सुखाकर लाइए, J-फॉर्म सँभालकर रखिए, और भुगतान की स्थिति ऐप पर खुद देखते रहिए।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        यह लेख सामान्य जानकारी के लिए है। समर्थन मूल्य, तारीख़ें और पंजीकरण के नियम सरकार के आदेशों से तय होते हैं और बदलते रहते हैं। KrashiMitra न सरकारी एजेंट है, न किसी का पंजीकरण करता है, न फसल खरीदता या बिकवाता है — अंतिम पुष्टि हमेशा <strong>fasal.haryana.gov.in</strong>, अपनी मार्केट कमेटी या हेल्पलाइन से ही कीजिए।
      </div>
    </div>
  </section>
"""

FAQS = [
    ("हरियाणा में धान की सरकारी खरीद 2026 में कब शुरू हुई?",
     "हरियाणा की मंडियों में 2026 में धान की <strong>तुलाई 24 सितंबर से</strong> और ई-खरीद पर <strong>गेट पास 25 सितंबर से</strong> शुरू हुए। तारीख़ें सरकार के आदेश से तय होती हैं, इसलिए अपनी मंडी की स्थिति मार्केट कमेटी से पुष्टि कर लीजिए।"),
    ("मेरी फसल मेरा ब्यौरा पर पंजीकरण के बिना धान MSP पर बिकता है?",
     "नहीं — हरियाणा में समर्थन मूल्य पर सरकारी खरीद <strong>उसी फसल की होती है जो मेरी फसल मेरा ब्यौरा पोर्टल पर दर्ज है</strong>। खरीफ 2026 की अंतिम तारीख 31 जुलाई थी और छूटे किसानों के लिए पोर्टल 21 से 27 सितंबर तक दोबारा खोला गया।"),
    ("धान का MSP 2026-27 कितना है?",
     "खरीफ विपणन वर्ष 2026-27 में धान का समर्थन मूल्य <strong>सामान्य ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल</strong> है, जो पिछले साल से ₹72 अधिक है। बासमती धान समर्थन मूल्य पर नहीं खरीदा जाता।"),
    ("मेरी फसल मेरा ब्यौरा पंजीकरण के लिए कौन-से कागज़ चाहिए?",
     "पंजीकरण के लिए <strong>परिवार पहचान पत्र, आधार और उससे जुड़ा मोबाइल, जमाबंदी या फर्द की नकल (खसरा-खेवट नंबर) और अपने नाम का चालू बैंक खाता</strong> चाहिए। पंजीकरण fasal.haryana.gov.in पर खुद या अटल सेवा केंद्र / CSC से कराया जा सकता है।"),
    ("J-फॉर्म क्या होता है?",
     "J-फॉर्म <strong>मंडी में धान बिकने की सरकारी पर्ची</strong> है, जिसमें मात्रा, भाव और रकम दर्ज होती है। भुगतान इसी के आधार पर होता है, और इसे eKharid Haryana ऐप पर भी देखा जा सकता है।"),
    ("धान बेचने के बाद पैसा कितने दिन में आता है?",
     "हरियाणा के मुख्य सचिव का निर्देश है कि किसान को <strong>J-फॉर्म कटने के 72 घंटे के भीतर</strong> भुगतान सीधे बैंक खाते में मिले। देर होने पर J-फॉर्म लेकर मार्केट कमेटी से मिलिए या ई-खरीद हेल्पलाइन 1800-180-2060 पर शिकायत कीजिए।"),
    ("धान में कितनी नमी चलती है?",
     "सरकारी खरीद में धान की अधिकतम नमी <strong>17%</strong> है। इसके अलावा अकार्बनिक और कार्बनिक अपद्रव्य 1%-1%, क्षतिग्रस्त दाने 5% और अपरिपक्व दाने 3% तक ही मान्य हैं।"),
    ("मेरी फसल मेरा ब्यौरा का हेल्पलाइन नंबर क्या है?",
     "पोर्टल पर MFMB हेल्पलाइन <strong>1800 180 2117</strong> और किसान कॉल सेंटर <strong>1800 180 2060</strong> दिए गए हैं, जो सोमवार से शुक्रवार सुबह 9 से शाम 5 बजे तक चलते हैं। ई-खरीद की टोल-फ्री हेल्पलाइन भी 1800-180-2060 है।"),
]

ARTICLE = {
    "slug": "haryana-dhan-kharid",
    "date": "2026-09-28",
    "date_label": "सितंबर 2026",
    "read_time": 9,
    "word_count": 2100,
    "lang": "hi",

    "section": "सरकारी योजना",
    "cat_label": "सरकारी योजना",
    "cat_query": "jankari",
    "breadcrumb_leaf": "हरियाणा धान खरीद",

    "title": "हरियाणा धान खरीद 2026: MSP ₹2,441, मेरी फसल मेरा ब्यौरा व गेट पास",
    "description": "हरियाणा में धान की तुलाई 24 सितंबर 2026 से। MSP ₹2,441, मेरी फसल मेरा ब्यौरा पंजीकरण, गेट पास, J-फॉर्म, नमी 17% और भुगतान कब — पूरी प्रक्रिया।",
    "keywords": "हरियाणा धान खरीद 2026, haryana dhan kharid, meri fasal mera byora, मेरी फसल मेरा ब्यौरा पंजीकरण, e kharid haryana, ई खरीद गेट पास, j form haryana, धान MSP 2441, haryana paddy procurement 2026, fasal.haryana.gov.in",

    "og_title": "हरियाणा धान खरीद 2026: MSP ₹2,441, मेरी फसल मेरा ब्यौरा व गेट पास",
    "og_desc": "हरियाणा में धान की तुलाई 24 सितंबर 2026 से। पंजीकरण, गेट पास, J-फॉर्म, नमी 17% और भुगतान कब — पूरी प्रक्रिया।",
    "hero_image": ("images/articles/haryana-dhan-kharid.webp",
                   "हरियाणा के गाँव में धान के खेतों के बीच से गुज़रती सड़क",
                   "हरियाणा के एक गाँव में धान के खेत — यही फसल मंडी में समर्थन मूल्य पर बिकती है। (मंडी की कोई स्वतंत्र-लाइसेंस वाली तस्वीर उपलब्ध नहीं है।)"),
    "headline": "हरियाणा धान खरीद 2026-27 — मेरी फसल मेरा ब्यौरा से मंडी और भुगतान तक",
    "headline_en": "Haryana Paddy Procurement 2026-27 — Registration, Gate Pass, J-Form &amp; Payment",
    "schema_desc": "हरियाणा में समर्थन मूल्य पर धान बेचने के लिए मेरी फसल मेरा ब्यौरा पंजीकरण, ज़रूरी दस्तावेज़, 2026 की तारीख़ें, ई-खरीद गेट पास, J-फॉर्म, नमी व गुणवत्ता मानक और भुगतान की पूरी प्रक्रिया।",
    "schema_keywords": ["हरियाणा धान खरीद", "Meri Fasal Mera Byora", "e-Kharid", "MSP",
                        "समर्थन मूल्य", "J-form", "हरियाणा"],

    "h1": "हरियाणा धान खरीद 2026-27",
    "h1_en": "Selling Paddy at MSP in Haryana — Registration, Mandi &amp; Payment",
    "share_title": "हरियाणा धान खरीद 2026-27 — MSP ₹2,441 पर धान बेचने की पूरी प्रक्रिया",
    "hero_excerpt": "समर्थन मूल्य ₹2,441 है, पर मंडी में धान तभी तुलता है जब फसल मेरी फसल मेरा ब्यौरा पर दर्ज हो।",
    "lede_h2": "मंडी के गेट से पहले पोर्टल का दरवाज़ा",

    "badges": [("badge-location", "📍 हरियाणा"),
               ("badge-season", "🗓️ सितंबर – नवंबर"),
               ("badge-disease", "🧾 MFMB पंजीकरण अनिवार्य")],

    "quick_facts": [("", "💰", "₹2,441", "सामान्य धान का MSP, प्रति क्विंटल"),
                    ("warn", "📅", "24 सितंबर", "2026 में मंडियों में तुलाई शुरू"),
                    ("danger", "💧", "17%", "इससे ऊपर नमी तो धान नहीं बिकता")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-common", "धान का भाव"),
                   ("paddy-basmati", "बासमती धान का भाव"),
                   ("wheat", "गेहूं का भाव"),
                   ("mustard", "सरसों का भाव")],

    "card": {
        "emoji": "🧾", "bg": "#eff6ff", "accent": "#0369a1",
        "tag": "हरियाणा धान खरीद", "tag_bg": "#dbeafe", "tag_color": "#0369a1",
        "title": "हरियाणा धान खरीद 2026-27 — मेरी फसल मेरा ब्यौरा से मंडी और भुगतान तक",
        "cats": "jankari",
        "keywords": "हरियाणा धान खरीद haryana dhan kharid meri fasal mera byora e kharid gate pass j form MSP 2441 नमी 17% भुगतान मंडी",
    },

    "related": [
        (f"{SITE}/articles/punjab-dhan-kharid", "#0369a1", "🧾", "पंजाब · धान खरीद",
         "पंजाब धान खरीद 2026-27 — अनाज खरीद पोर्टल और सीधा भुगतान"),
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
