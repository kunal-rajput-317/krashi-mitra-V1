# -*- coding: utf-8 -*-
# Bihar paddy procurement (धान अधिप्राप्ति), KMS 2026-27. Written 28 Sep 2026.
#
# Sources (every figure below traces to one of these):
#   MSP ₹2,441 / ₹2,461 (+₹72): CCEA, PIB PRID 2260617.
#   esahkari.bihar.gov.in/coop/MIS/FarmerReg/PaddyFarmerReg.aspx — read on
#     28 Sep 2026: the application needs the कृषि विभाग किसान निबंधन संख्या
#     (register first if you have none; correct it via the संशोधन link);
#     OTP on the registered mobile, one number only; no edits after final
#     submit; raiyat farmers enter the jamabandi register भाग and पृष्ठ
#     number; max 250 quintal raiyat, 100 quintal non-raiyat; KMS 2025-26
#     procurement began 1 November 2025, sell at any procurement centre of
#     your choice; technical help 0612-2506307 and 1800 1800 110; header
#     1800 3454 110 (toll free) and 0612-2200693 (कृषि विभाग). On that date
#     the page still offered the 2025-26 paddy form, not a 2026-27 one.
#   KMS 2025-26 ran November 2025 – February 2026 through panchayat PACS and
#     block-level व्यापार मंडल; payment straight to the farmer's bank account
#     through PFMS; toll-free 1800 1800 110: Indian Masterminds.
#   Quality specs (17% moisture …): FCI uniform specifications.
# Deliberately NOT claimed: that the 2026-27 form is open, a payment deadline
# in hours (only unofficial sites state one), the non-raiyat paperwork.
SITE = "https://krashimitra.in"

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>भूमिका</h2>
    </div>
    <p>
      बिहार में धान की सरकारी खरीद — जिसे यहाँ <strong>धान अधिप्राप्ति</strong> कहते हैं — पंचायत के <strong>पैक्स (PACS)</strong> और प्रखंड के <strong>व्यापार मंडल</strong> करते हैं। खरीफ विपणन वर्ष 2026-27 में समर्थन मूल्य <strong>₹2,441 प्रति क्विंटल</strong> है। पर पैक्स में धान तभी बिकता है जब आपने सहकारिता विभाग के पोर्टल पर <strong>धान अधिप्राप्ति का आवेदन</strong> किया हो — और उससे पहले कृषि विभाग में <strong>किसान निबंधन</strong> कराया हो।
    </p>
    <p>
      यानी पंजीकरण दो सीढ़ियों का है, और ज़्यादातर किसान पहली सीढ़ी पर ही अटकते हैं। इस लेख में दोनों सीढ़ियाँ क्रम से हैं, साथ में रैयत और गैर-रैयत किसान की सीमा, पैक्स पर नमी की शर्त, और पैसा कैसे आता है।
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
      <h2>बिहार में धान अधिप्राप्ति कैसे होती है?</h2>
    </div>
    <ul>
      <li><strong>कौन खरीदता है:</strong> पंचायत स्तर के पैक्स और प्रखंड स्तर के व्यापार मंडल।</li>
      <li><strong>किसका धान:</strong> उसी किसान का, जिसका सहकारिता विभाग के पोर्टल पर धान अधिप्राप्ति का आवेदन दर्ज है।</li>
      <li><strong>कहाँ बेचें:</strong> पिछले साल विभाग ने साफ़ लिखा था कि किसान <strong>अपनी पसंद के किसी भी अधिप्राप्ति केंद्र</strong> पर धान बेच सकता है।</li>
      <li><strong>भुगतान:</strong> PFMS के ज़रिए <strong>सीधे किसान के बैंक खाते में</strong>।</li>
    </ul>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        पैक्स में धान बेचने का सबसे बड़ा फ़ायदा तय भाव और लिखित रिकॉर्ड है। शर्त बस एक है — <strong>आवेदन समय पर, और सही ब्यौरे के साथ</strong>।
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
      केंद्रीय मंत्रिमंडल ने खरीफ विपणन वर्ष <strong>2026-27</strong> के लिए धान का समर्थन मूल्य <strong>₹72 प्रति क्विंटल</strong> बढ़ाया है। यही दर पैक्स और व्यापार मंडल की खरीद पर लागू होती है।
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
      यानी सामान्य धान <strong>₹24.41 प्रति किलो</strong>। गाँव में व्यापारी जो भाव बोल रहा है, उससे मिलाकर देखिए — फ़र्क अक्सर प्रति क्विंटल सैकड़ों रुपये का होता है। आज का भाव <a href="https://krashimitra.in/bhav/paddy-common">धान का मंडी भाव</a> पर देखिए।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- LIMITS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📊</span>
      <h2>रैयत और गैर-रैयत — कितना धान बिकेगा</h2>
    </div>
    <p>
      सहकारिता विभाग के पोर्टल पर एक किसान से खरीद की <strong>अधिकतम सीमा</strong> तय है:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>किसान का प्रकार</th><th>मतलब</th><th>अधिकतम धान</th></tr>
      </thead>
      <tbody>
        <tr><td>रैयत</td><td>अपनी ज़मीन पर खेती करने वाला</td><td><strong>250 क्विंटल</strong></td></tr>
        <tr><td>गैर-रैयत</td><td>दूसरे की ज़मीन पर (बटाई / किराये पर) खेती करने वाला</td><td><strong>100 क्विंटल</strong></td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        ये सीमाएँ पोर्टल पर पिछले सीज़न के लिए दर्ज हैं। 2026-27 में कोई बदलाव हो तो वह विभाग की अधिसूचना में आएगा — आवेदन के समय पोर्टल पर लिखी सीमा ही मानिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- DATES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>आवेदन और खरीद कब होती है?</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>काम</th><th>स्थिति</th></tr>
      </thead>
      <tbody>
        <tr><td>2025-26 में खरीद की शुरुआत</td><td>1 नवंबर 2025</td></tr>
        <tr><td>2025-26 में खरीद की अवधि</td><td>नवंबर 2025 से फरवरी 2026</td></tr>
        <tr><td>2026-27 का आवेदन</td><td>सहकारिता विभाग के पोर्टल पर खुलने की सूचना देखते रहिए</td></tr>
      </tbody>
    </table>
    <p>
      28 सितंबर 2026 को सहकारिता विभाग के पोर्टल पर धान का आवेदन पत्र अभी 2025-26 का ही दिख रहा था। इस बीच जो काम अभी हो सकता है, वह है <strong>कृषि विभाग का किसान निबंधन</strong> — वह न हो तो धान का आवेदन हो ही नहीं सकता।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 2 ── -->
  <div class="ad-slot responsive" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="4489195916" data-format="auto"></div>
    </div>
  </div>

  <!-- HOW TO REGISTER -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💻</span>
      <h2>आवेदन कैसे करें — दो सीढ़ियाँ</h2>
    </div>
    <p><strong>पहली सीढ़ी: कृषि विभाग का किसान निबंधन</strong></p>
    <ul>
      <li><strong>निबंधन संख्या:</strong> धान अधिप्राप्ति के आवेदन में सबसे पहले <strong>कृषि विभाग की किसान निबंधन संख्या</strong> माँगी जाती है।</li>
      <li><strong>नहीं है तो:</strong> सहकारिता विभाग के आवेदन पेज पर ही "किसान पंजीकरण" का लिंक है — वहाँ से पहले निबंधन कराइए।</li>
      <li><strong>गलती है तो:</strong> निबंधन के ब्यौरे में कोई त्रुटि हो तो "किसान पंजीकरण संशोधन" लिंक से सुधारिए।</li>
    </ul>
    <p><strong>दूसरी सीढ़ी: धान अधिप्राप्ति का आवेदन (सहकारिता विभाग)</strong></p>
    <ol>
      <li><strong>पोर्टल खोलिए:</strong> esahkari.bihar.gov.in पर धान अधिप्राप्ति का आवेदन पत्र चुनिए।</li>
      <li><strong>निबंधन संख्या डालिए:</strong> कृषि विभाग की किसान निबंधन संख्या भरिए।</li>
      <li><strong>OTP:</strong> पंजीकृत मोबाइल पर OTP आता है। <strong>एक ही मोबाइल नंबर</strong> इस्तेमाल कीजिए, और OTP किसी को मत बताइए।</li>
      <li><strong>ज़मीन का ब्यौरा (रैयत):</strong> जमाबंदी पंजी का <strong>भाग संख्या और पृष्ठ संख्या</strong> भरना होता है — यह न पता हो तो पोर्टल पर इसे जानने का लिंक दिया है।</li>
      <li><strong>जाँचकर फ़ाइनल सबमिट:</strong> सबमिट से पहले हर जानकारी दोबारा पढ़िए — <strong>फ़ाइनल सबमिट के बाद संशोधन की अनुमति नहीं है</strong>। फिर आवेदन का प्रिंट निकाल लीजिए।</li>
    </ol>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        तकनीकी समस्या होने पर सहकारिता विभाग के नंबर <strong>0612-2506307</strong> और <strong>1800 1800 110</strong> पर संपर्क कीजिए। कृषि विभाग के निबंधन से जुड़ी बात के लिए पोर्टल पर <strong>1800 3454 110</strong> (टोल-फ्री) और <strong>0612-2200693</strong> दिए गए हैं।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- FREE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🆓</span>
      <h2>आवेदन के पैसे किसी को मत दीजिए</h2>
    </div>
    <p>
      किसान निबंधन और धान अधिप्राप्ति का आवेदन <strong>सरकारी व्यवस्था का हिस्सा है, इसके लिए कोई शुल्क नहीं है</strong>। साइबर कैफ़े या वसुधा केंद्र अपनी टाइपिंग-प्रिंट की मामूली फ़ीस ले सकते हैं; "पैक्स में पक्की बिक्री" के नाम पर पैसे माँगे जाएँ तो वह वसूली है।
    </p>
    <ul>
      <li><strong>अपना बैंक खाता खुद जाँचिए:</strong> भुगतान उसी खाते में आता है जो निबंधन में दर्ज है।</li>
      <li><strong>अपने नाम से ही बेचिए:</strong> किसी दूसरे के आवेदन पर अपना धान या अपने आवेदन पर किसी और का धान — दोनों ही जोखिम भरे हैं।</li>
      <li><strong>प्रिंट सँभालकर रखिए:</strong> पैक्स पर और भुगतान की शिकायत में यही काम आता है।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- AT THE PACS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">⚖️</span>
      <h2>पैक्स पर क्या-क्या होता है</h2>
    </div>
    <p>
      पैक्स या व्यापार मंडल पर पहले धान की <strong>गुणवत्ता जाँच</strong> होती है, फिर तौल और खरीद का रिकॉर्ड। जाँच का पहला पैमाना नमी है।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>पैमाना</th><th>अधिकतम सीमा</th><th>इसका मतलब</th></tr>
      </thead>
      <tbody>
        <tr><td>नमी</td><td><strong>17.0%</strong></td><td>इससे ज़्यादा पर धान नहीं लिया जाता</td></tr>
        <tr><td>अकार्बनिक अपद्रव्य</td><td>1.0%</td><td>मिट्टी, कंकड़, धूल</td></tr>
        <tr><td>कार्बनिक अपद्रव्य</td><td>1.0%</td><td>पुआल, डंठल, खरपतवार के बीज</td></tr>
        <tr><td>क्षतिग्रस्त, विवर्णित, अंकुरित व घुन लगे दाने</td><td>5.0%</td><td>बारिश में भीगा या ढेर में गरम हुआ धान</td></tr>
        <tr><td>अपरिपक्व, सिकुड़े व झुर्रीदार दाने</td><td>3.0%</td><td>जल्दी काटी फसल</td></tr>
      </tbody>
    </table>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        तौल की पर्ची लिए बिना मत लौटिए। धान सुखाने का पूरा तरीका <a href="https://krashimitra.in/articles/dhan-nami-mandi-rejection">धान में नमी 17% का पूरा नियम</a> में दिया है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- PAYMENT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏦</span>
      <h2>भुगतान कैसे आता है?</h2>
    </div>
    <p>
      धान का भुगतान <strong>PFMS के ज़रिए सीधे आपके बैंक खाते में</strong> भेजा जाता है — वही खाता जो निबंधन में दर्ज है। नकद भुगतान सरकारी खरीद में नहीं होता।
    </p>
    <ul>
      <li><strong>खाता चालू हो:</strong> बंद या निष्क्रिय खाते में भुगतान लौट आता है।</li>
      <li><strong>नाम मेल खाए:</strong> निबंधन, आधार और बैंक खाते में नाम की वर्तनी एक जैसी हो।</li>
      <li><strong>देर होने पर:</strong> आवेदन का प्रिंट और तौल पर्ची लेकर पैक्स अध्यक्ष या प्रखंड सहकारिता पदाधिकारी से मिलिए, या 1800 1800 110 पर बात कीजिए।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- MISTAKES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚫</span>
      <h2>ये गलतियाँ कभी न करें</h2>
    </div>
    <ul>
      <li><strong>किसान निबंधन के बिना सीधे धान का आवेदन खोजना</strong> — पहली सीढ़ी निबंधन है।</li>
      <li><strong>बिना जाँचे फ़ाइनल सबमिट करना</strong> — उसके बाद सुधार की अनुमति नहीं है।</li>
      <li><strong>अलग-अलग मोबाइल नंबर इस्तेमाल करना</strong> — OTP उसी नंबर पर आता है जो पंजीकृत है।</li>
      <li><strong>सीमा से ज़्यादा धान की उम्मीद रखना</strong> — रैयत के लिए 250 और गैर-रैयत के लिए 100 क्विंटल की सीमा पोर्टल पर दर्ज है।</li>
      <li><strong>गीला धान लेकर पैक्स पहुँचना</strong> — 17% से ज़्यादा नमी पर धान लौटता है।</li>
      <li><strong>तौल पर्ची न लेना</strong> — भुगतान और शिकायत, दोनों इसी पर टिकते हैं।</li>
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
        <tr><td>अभी</td><td>कृषि विभाग का किसान निबंधन है या नहीं, जाँचना; गलती हो तो सुधारना</td></tr>
        <tr><td>आवेदन खुलने पर</td><td>सहकारिता विभाग के पोर्टल पर धान अधिप्राप्ति का आवेदन; जाँचकर फ़ाइनल सबमिट; प्रिंट</td></tr>
        <tr><td>कटाई के बाद</td><td>सुखाई और सफ़ाई — नमी 17% से नीचे</td></tr>
        <tr><td>खरीद शुरू होने पर</td><td>पैक्स या व्यापार मंडल पर जाँच, तौल, पर्ची</td></tr>
        <tr><td>बिक्री के बाद</td><td>बैंक खाते में भुगतान देखना; न आए तो शिकायत</td></tr>
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
      बिहार में समर्थन मूल्य का रास्ता दो पोर्टल से होकर जाता है: पहले <strong>कृषि विभाग का किसान निबंधन</strong>, फिर <strong>सहकारिता विभाग पर धान अधिप्राप्ति का आवेदन</strong>। पहला काम आज ही कर लीजिए, दूसरा आवेदन खुलते ही — और फ़ाइनल सबमिट से पहले हर ब्यौरा दो बार पढ़िए, क्योंकि उसके बाद सुधार नहीं होता।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        यह लेख सामान्य जानकारी के लिए है। समर्थन मूल्य, तारीख़ें, सीमाएँ और आवेदन के नियम सरकार की अधिसूचनाओं से तय होते हैं और बदलते रहते हैं। KrashiMitra न सरकारी एजेंट है, न किसी का आवेदन भरता है, न फसल खरीदता या बिकवाता है — अंतिम पुष्टि हमेशा <strong>esahkari.bihar.gov.in</strong>, अपने पैक्स या प्रखंड सहकारिता पदाधिकारी से ही कीजिए।
      </div>
    </div>
  </section>
"""

FAQS = [
    ("बिहार में धान अधिप्राप्ति का आवेदन कहाँ होता है?",
     "धान अधिप्राप्ति का आवेदन बिहार सरकार के <strong>सहकारिता विभाग के पोर्टल (esahkari.bihar.gov.in)</strong> पर होता है। आवेदन में कृषि विभाग की किसान निबंधन संख्या माँगी जाती है, इसलिए पहले किसान निबंधन ज़रूरी है।"),
    ("रैयत और गैर-रैयत किसान कितना धान बेच सकते हैं?",
     "सहकारिता विभाग के पोर्टल के अनुसार <strong>रैयत किसान अधिकतम 250 क्विंटल</strong> और <strong>गैर-रैयत किसान अधिकतम 100 क्विंटल</strong> धान बेच सकते हैं। 2026-27 की अंतिम सीमा आवेदन के समय पोर्टल पर लिखी सीमा ही मानिए।"),
    ("धान का MSP 2026-27 कितना है?",
     "खरीफ विपणन वर्ष 2026-27 में धान का समर्थन मूल्य <strong>सामान्य ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल</strong> है, जो पिछले साल से ₹72 अधिक है। यही दर पैक्स और व्यापार मंडल की खरीद पर लागू होती है।"),
    ("बिहार में धान की खरीद कब से शुरू होती है?",
     "पिछले सीज़न (2025-26) में बिहार में धान अधिप्राप्ति <strong>1 नवंबर 2025</strong> से शुरू होकर फरवरी 2026 तक चली। 2026-27 की तारीख़ के लिए सहकारिता विभाग के पोर्टल या अपने पैक्स से संपर्क में रहिए।"),
    ("क्या अपने पंचायत के पैक्स में ही धान बेचना ज़रूरी है?",
     "नहीं — पिछले सीज़न में विभाग ने पोर्टल पर लिखा था कि किसान <strong>अपनी पसंद के किसी भी अधिप्राप्ति केंद्र</strong> पर धान बेच सकता है। खरीद पंचायत के पैक्स और प्रखंड के व्यापार मंडल करते हैं।"),
    ("फ़ाइनल सबमिट के बाद आवेदन में सुधार हो सकता है?",
     "नहीं — पोर्टल के निर्देश के अनुसार <strong>फ़ाइनल सबमिट के बाद संशोधन की अनुमति नहीं है</strong>। इसलिए सबमिट से पहले हर जानकारी दोबारा जाँचिए; किसान निबंधन के ब्यौरे की गलती अलग ‘किसान पंजीकरण संशोधन’ लिंक से सुधरती है।"),
    ("धान अधिप्राप्ति का हेल्पलाइन नंबर क्या है?",
     "तकनीकी समस्या के लिए सहकारिता विभाग के नंबर <strong>0612-2506307</strong> और <strong>1800 1800 110</strong> हैं। कृषि विभाग के निबंधन से जुड़ी बात के लिए पोर्टल पर 1800 3454 110 (टोल-फ्री) और 0612-2200693 दिए गए हैं।"),
    ("धान में कितनी नमी चलती है?",
     "सरकारी खरीद में धान की अधिकतम नमी <strong>17%</strong> है। इसके अलावा अकार्बनिक और कार्बनिक अपद्रव्य 1%-1%, क्षतिग्रस्त दाने 5% और अपरिपक्व दाने 3% तक ही मान्य हैं।"),
]

ARTICLE = {
    "slug": "bihar-dhan-adhiprapti",
    "date": "2026-09-28",
    "date_label": "सितंबर 2026",
    "read_time": 8,
    "word_count": 1900,
    "lang": "hi",

    "section": "सरकारी योजना",
    "cat_label": "सरकारी योजना",
    "cat_query": "jankari",
    "breadcrumb_leaf": "बिहार धान अधिप्राप्ति",

    "title": "बिहार धान अधिप्राप्ति 2026-27: MSP ₹2,441, पैक्स में बेचने का आवेदन",
    "description": "बिहार में पैक्स पर धान बेचने के लिए किसान निबंधन और सहकारिता विभाग पर आवेदन। रैयत 250, गैर-रैयत 100 क्विंटल की सीमा, MSP ₹2,441, नमी 17% — पूरी प्रक्रिया।",
    "keywords": "बिहार धान अधिप्राप्ति 2026-27, bihar dhan adhiprapti, bihar paddy procurement, esahkari bihar, पैक्स धान खरीद, pacs dhan bikri, धान अधिप्राप्ति आवेदन, रैयत गैर रैयत 250 क्विंटल, धान MSP 2441, किसान निबंधन बिहार",

    "og_title": "बिहार धान अधिप्राप्ति 2026-27: MSP ₹2,441, पैक्स में बेचने का आवेदन",
    "og_desc": "किसान निबंधन और सहकारिता विभाग पर आवेदन। रैयत 250, गैर-रैयत 100 क्विंटल की सीमा, MSP ₹2,441, नमी 17% — पूरी प्रक्रिया।",
    "hero_image": ("images/articles/bihar-dhan-adhiprapti.webp",
                   "बिहार के दरभंगा के पास धान के खेत",
                   "बिहार के दरभंगा के पास धान के खेत — यही फसल पैक्स में समर्थन मूल्य पर बिकती है। (पैक्स केंद्र की कोई स्वतंत्र-लाइसेंस वाली तस्वीर उपलब्ध नहीं है।)"),
    "headline": "बिहार धान अधिप्राप्ति 2026-27 — किसान निबंधन से पैक्स और भुगतान तक",
    "headline_en": "Bihar Paddy Procurement 2026-27 — Registration, PACS &amp; Payment",
    "schema_desc": "बिहार में पैक्स और व्यापार मंडल पर समर्थन मूल्य पर धान बेचने के लिए कृषि विभाग का किसान निबंधन, सहकारिता विभाग पर धान अधिप्राप्ति आवेदन, रैयत-गैर रैयत सीमा, नमी व गुणवत्ता मानक और PFMS से भुगतान की पूरी प्रक्रिया।",
    "schema_keywords": ["बिहार धान अधिप्राप्ति", "Bihar paddy procurement", "PACS", "MSP",
                        "समर्थन मूल्य", "सहकारिता विभाग", "बिहार"],

    "h1": "बिहार धान अधिप्राप्ति 2026-27",
    "h1_en": "Selling Paddy at MSP in Bihar — Registration, PACS &amp; Payment",
    "share_title": "बिहार धान अधिप्राप्ति 2026-27 — MSP ₹2,441 पर पैक्स में धान बेचने की पूरी प्रक्रिया",
    "hero_excerpt": "पैक्स में धान तभी बिकता है जब दो सीढ़ियाँ पूरी हों: कृषि विभाग का किसान निबंधन, फिर सहकारिता विभाग पर आवेदन।",
    "lede_h2": "दो पोर्टल, दो सीढ़ियाँ, एक तय भाव",

    "badges": [("badge-location", "📍 बिहार"),
               ("badge-season", "🗓️ नवंबर – फरवरी"),
               ("badge-disease", "🧾 आवेदन अनिवार्य")],

    "quick_facts": [("", "💰", "₹2,441", "सामान्य धान का MSP, प्रति क्विंटल"),
                    ("warn", "🌾", "250 / 100", "रैयत / गैर-रैयत की अधिकतम सीमा, क्विंटल"),
                    ("danger", "💧", "17%", "इससे ऊपर नमी तो धान नहीं लिया जाता")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-common", "धान का भाव"),
                   ("wheat", "गेहूं का भाव"),
                   ("maize", "मक्का का भाव")],

    "card": {
        "emoji": "🧾", "bg": "#eff6ff", "accent": "#0369a1",
        "tag": "बिहार धान अधिप्राप्ति", "tag_bg": "#dbeafe", "tag_color": "#0369a1",
        "title": "बिहार धान अधिप्राप्ति 2026-27 — किसान निबंधन से पैक्स और भुगतान तक",
        "cats": "jankari",
        "keywords": "बिहार धान अधिप्राप्ति bihar dhan adhiprapti paddy procurement pacs पैक्स व्यापार मंडल esahkari रैयत गैर रैयत 250 100 क्विंटल MSP 2441 नमी 17% PFMS",
    },

    "related": [
        (f"{SITE}/articles/chhattisgarh-dhan-kharidi", "#0369a1", "🧾", "छत्तीसगढ़ · धान खरीदी",
         "छत्तीसगढ़ धान खरीदी 2026-27 — एग्री स्टैक पंजीयन 31 अक्टूबर तक"),
        (f"{SITE}/articles/up-dhan-kharid-panjikaran", "#0369a1", "🧾", "UP · धान खरीद",
         "UP धान खरीद पंजीकरण — MSP ₹2,441 पर धान बेचने की पूरी प्रक्रिया"),
        (f"{SITE}/articles/dhan-nami-mandi-rejection", "#0f766e", "💧", "धान · गुणवत्ता",
         "धान में नमी कितनी होनी चाहिए? 17% का पूरा नियम"),
        (f"{SITE}/articles/machhli-palan-bihar", "#0e7490", "🐟", "बिहार · मछली पालन",
         "बिहार में मछली पालन — शुरुआत की पूरी जानकारी"),
        (f"{SITE}/bhav/paddy-common", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "धान का आज का मंडी भाव — राज्यवार LIVE रेट"),
    ],
}
