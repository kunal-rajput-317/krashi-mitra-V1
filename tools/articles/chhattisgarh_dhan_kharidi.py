# -*- coding: utf-8 -*-
# Chhattisgarh paddy procurement (धान खरीदी), KMS 2026-27. Written 28 Sep 2026.
#
# Sources (every figure below traces to one of these):
#   MSP ₹2,441 / ₹2,461 (+₹72): CCEA, PIB PRID 2260617.
#   2026-27: registration on the central Agri Stack portal is mandatory before
#     selling at MSP; deadline 31 October; societies get a login to register
#     farmers (khasra, bank and nominee details); ~28 lakh farmers already
#     registered: Patrika (Raipur), Tractor Junction, Rewa Riyasat.
#   360 new purchase centres, 3.64 lakh bales of gunny bags: food minister's
#     review, 25 Sep 2026 (palpalindia, news24bharat).
#   KMS 2025-26: purchase 15 Nov 2025 – 31 Jan 2026, ₹3,100 per quintal set by
#     the state cabinet, 21 quintal per acre, online tokens via the "टोकन तुंहर
#     हाथ" app: Drishti IAS, Krishak Jagat. Offline tokens from the society
#     allowed from Jan 2026: ETV Bharat, 13 Jan 2026.
#   The part above MSP reaches farmers later, as a lump sum under कृषक उन्नति
#     योजना: The Hawk, Indian Masterminds (budget provisions).
#   Quality specs (17% moisture …): FCI uniform specifications.
# Deliberately NOT claimed: the 2026-27 purchase dates, the 2026-27 state rate
# or per-acre limit (none announced as of 28 Sep 2026), any helpline number,
# any payment deadline in hours. The page says these are still to come.
SITE = "https://krashimitra.in"

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>भूमिका</h2>
    </div>
    <p>
      छत्तीसगढ़ में खरीफ विपणन वर्ष 2026-27 की धान खरीदी से पहले एक बड़ा नियम बदला है: <strong>समर्थन मूल्य पर धान बेचने के लिए केंद्र सरकार के एग्री स्टैक (Agri Stack) पोर्टल पर पंजीयन अनिवार्य</strong> कर दिया गया है, और इसकी अंतिम तिथि <strong>31 अक्टूबर</strong> है। लगभग 28 लाख किसान पंजीयन करा चुके हैं — जो बाकी हैं, उनके लिए यही सबसे ज़रूरी काम है।
    </p>
    <p>
      खरीदी की तारीख़ें और इस साल का भाव सरकार ने अभी घोषित नहीं किया है। इस लेख में वह सब है जो अभी पक्का है — पंजीयन कहाँ और कैसे होगा, केंद्र का समर्थन मूल्य, पिछले साल खरीदी कैसे चली, टोकन क्या है, और समिति पर धान किन शर्तों पर तुलता है — ताकि घोषणा होते ही आप तैयार हों।
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
      <h2>छत्तीसगढ़ में धान खरीदी कैसे होती है?</h2>
    </div>
    <p>
      छत्तीसगढ़ में धान मंडियों में नहीं, <strong>सहकारी समितियों के उपार्जन केंद्रों</strong> पर खरीदा जाता है। किसान पहले पंजीयन कराता है, फिर <strong>टोकन</strong> लेता है — टोकन में तय होता है कि वह किस दिन कितना धान लेकर केंद्र पर आएगा। केंद्र पर धान की जाँच, तौल और खरीदी होती है, और भुगतान पंजीयन में दर्ज बैंक खाते में आता है।
    </p>
    <p>
      2026-27 के लिए सरकार ने प्रदेश में <strong>360 नए खरीदी केंद्र</strong> खोलने और <strong>3.64 लाख गठान नए जूट बारदाने</strong> की व्यवस्था करने की बात कही है, ताकि किसान को दूर न जाना पड़े और बारदाने की कमी न हो।
    </p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        पूरे रास्ते में पहली सीढ़ी पंजीयन है। <strong>बिना पंजीयन के टोकन नहीं कटता, और बिना टोकन के धान नहीं तुलता।</strong>
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- PRICE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💰</span>
      <h2>धान का भाव — समर्थन मूल्य और राज्य की राशि</h2>
    </div>
    <p>
      केंद्र सरकार ने खरीफ विपणन वर्ष <strong>2026-27</strong> के लिए धान का समर्थन मूल्य <strong>₹72 प्रति क्विंटल</strong> बढ़ाया है:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>श्रेणी</th><th>केंद्र का MSP 2026-27</th><th>पिछला वर्ष</th></tr>
      </thead>
      <tbody>
        <tr><td>धान — सामान्य (कॉमन)</td><td><strong>₹2,441 / क्विंटल</strong></td><td>₹2,369</td></tr>
        <tr><td>धान — ग्रेड A</td><td><strong>₹2,461 / क्विंटल</strong></td><td>₹2,389</td></tr>
      </tbody>
    </table>
    <p>
      छत्तीसगढ़ में किसान को इससे ज़्यादा मिलता रहा है। खरीफ विपणन वर्ष <strong>2025-26</strong> में राज्य मंत्रिमंडल ने धान <strong>₹3,100 प्रति क्विंटल</strong> की दर से, और हर किसान से <strong>एक एकड़ की उपज में से अधिकतम 21 क्विंटल</strong> खरीदने का फ़ैसला किया था। खरीदी के समय समर्थन मूल्य का भुगतान होता है, और बाकी अंतर की राशि <strong>कृषक उन्नति योजना</strong> के तहत बाद में एकमुश्त किसानों के खातों में भेजी गई।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        <strong>2026-27 की राज्य दर और प्रति एकड़ सीमा अभी घोषित नहीं हुई है।</strong> ₹3,100 और 21 क्विंटल पिछले सीज़न के आँकड़े हैं — इस साल क्या होगा, यह राज्य सरकार की धान खरीदी नीति से तय होगा। घोषणा के लिए अपनी सहकारी समिति या ज़िला खाद्य अधिकारी से संपर्क में रहिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- DATES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>2026-27 की तारीख़ें — क्या पक्का है, क्या बाकी है</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>काम</th><th>स्थिति</th></tr>
      </thead>
      <tbody>
        <tr><td>एग्री स्टैक पर पंजीयन की अंतिम तिथि</td><td><strong>31 अक्टूबर</strong></td></tr>
        <tr><td>धान खरीदी शुरू होने की तारीख़ 2026-27</td><td>अभी घोषित नहीं</td></tr>
        <tr><td>पिछले साल (2025-26) खरीदी की अवधि</td><td>15 नवंबर 2025 से 31 जनवरी 2026</td></tr>
      </tbody>
    </table>
    <p>
      पिछले साल खरीदी <strong>नवंबर के बीच</strong> से शुरू होकर <strong>जनवरी के अंत</strong> तक चली थी। इस साल भी खरीदी से पहले पंजीयन पूरा होना ज़रूरी है — 31 अक्टूबर के बाद का इंतज़ार मत कीजिए।
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

  <!-- AGRI STACK -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💻</span>
      <h2>एग्री स्टैक पंजीयन कहाँ और कैसे होगा</h2>
    </div>
    <p>
      एग्री स्टैक केंद्र सरकार की किसानों की डिजिटल रजिस्ट्री है, जिसमें किसान, उसकी ज़मीन और बैंक खाते का ब्यौरा एक जगह दर्ज होता है। 2026-27 में छत्तीसगढ़ में धान खरीदी इसी पंजीयन से जुड़ी है।
    </p>
    <ul>
      <li><strong>खुद पोर्टल पर:</strong> किसान एग्री स्टैक पोर्टल पर सीधे पंजीयन कर सकता है।</li>
      <li><strong>सहकारी समिति में:</strong> समितियों में भी एग्री स्टैक पंजीयन की सुविधा दी जा रही है — समिति प्रबंधकों को इसके लिए लॉगिन दिया गया है।</li>
      <li><strong>क्या-क्या भरा जाता है:</strong> ज़मीन का खसरा ब्यौरा, बैंक खाते की जानकारी और नॉमिनी (नामांकित व्यक्ति) का ब्यौरा।</li>
    </ul>
    <table class="article-table">
      <thead>
        <tr><th>साथ ले जाइए</th><th>किसलिए</th></tr>
      </thead>
      <tbody>
        <tr><td>आधार कार्ड और उससे जुड़ा मोबाइल</td><td>पहचान और OTP</td></tr>
        <tr><td>ज़मीन के कागज़ (खसरा नंबर, रकबा)</td><td>कितनी ज़मीन पर धान बोया है</td></tr>
        <tr><td>बैंक पासबुक</td><td>भुगतान इसी खाते में</td></tr>
        <tr><td>नॉमिनी का नाम और ब्यौरा</td><td>पंजीयन में नॉमिनी दर्ज होता है</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        पंजीयन की प्रक्रिया और ज़रूरी कागज़ों की अंतिम सूची आपकी सहकारी समिति बताएगी। पंजीयन के बाद अपनी <strong>पावती या पंजीयन संख्या</strong> ज़रूर लीजिए — खरीदी के समय यही काम आएगी।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- FREE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🆓</span>
      <h2>पंजीयन और टोकन के पैसे किसी को मत दीजिए</h2>
    </div>
    <p>
      एग्री स्टैक पंजीयन और धान बिक्री का टोकन <strong>सरकारी व्यवस्था का हिस्सा है, इसके लिए कोई शुल्क नहीं है</strong>। "जल्दी टोकन", "ज़्यादा मात्रा" या "पक्का पंजीयन" के नाम पर पैसे माँगे जाएँ तो वह वसूली है — समिति प्रबंधक या ज़िला प्रशासन से शिकायत कीजिए।
    </p>
    <ul>
      <li><strong>OTP किसी को न बताइए:</strong> OTP से आपका पंजीयन और बैंक खाता जुड़ता है।</li>
      <li><strong>अपना बैंक खाता खुद जाँचिए:</strong> गलत खाता दर्ज हुआ तो धान का पैसा वहीं जाएगा।</li>
      <li><strong>अपना धान अपने नाम से ही बेचिए:</strong> किसी और के पंजीयन पर धान बेचना या अपने पंजीयन पर किसी और का धान बिकवाना — दोनों जोखिम भरे हैं।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- TOKEN -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🎟️</span>
      <h2>टोकन क्या है — पिछले साल कैसे कटा</h2>
    </div>
    <p>
      टोकन वह पर्ची है जिससे तय होता है कि आप <strong>किस दिन, कितना धान</strong> लेकर समिति पर आएँगे — इससे केंद्र पर भीड़ बँटती है। 2025-26 में किसान <strong>"टोकन तुंहर हाथ"</strong> मोबाइल ऐप से ऑनलाइन टोकन ले रहे थे, और जनवरी 2026 से समिति से <strong>ऑफ़लाइन टोकन</strong> कटने की सुविधा भी शुरू हुई।
    </p>
    <div class="tip-box tip">
      <span class="tip-icon">🟡</span>
      <div class="tip-content">
        2026-27 में टोकन किस तरीके से कटेगा, यह खरीदी नीति में घोषित होगा। पंजीयन पूरा कर लीजिए — टोकन उसके बिना कटता ही नहीं।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- AT THE CENTRE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">⚖️</span>
      <h2>उपार्जन केंद्र पर क्या-क्या होता है</h2>
    </div>
    <p>
      टोकन के दिन धान लेकर समिति पहुँचिए। वहाँ धान की <strong>गुणवत्ता जाँच</strong> होती है, फिर बारदाने में भराई और तौल। जाँच का पहला पैमाना नमी है।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>पैमाना</th><th>अधिकतम सीमा</th><th>इसका मतलब</th></tr>
      </thead>
      <tbody>
        <tr><td>नमी</td><td><strong>17.0%</strong></td><td>इससे ज़्यादा पर धान नहीं तुलता</td></tr>
        <tr><td>अकार्बनिक अपद्रव्य</td><td>1.0%</td><td>मिट्टी, कंकड़, धूल</td></tr>
        <tr><td>कार्बनिक अपद्रव्य</td><td>1.0%</td><td>पुआल, डंठल, खरपतवार के बीज</td></tr>
        <tr><td>क्षतिग्रस्त, विवर्णित, अंकुरित व घुन लगे दाने</td><td>5.0%</td><td>बारिश में भीगा या ढेर में गरम हुआ धान</td></tr>
        <tr><td>अपरिपक्व, सिकुड़े व झुर्रीदार दाने</td><td>3.0%</td><td>जल्दी काटी फसल</td></tr>
      </tbody>
    </table>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        तौल की पर्ची और बिक्री का रिकॉर्ड लिए बिना केंद्र से मत लौटिए। धान सुखाने का पूरा तरीका <a href="https://krashimitra.in/articles/dhan-nami-mandi-rejection">धान में नमी 17% का पूरा नियम</a> में दिया है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- PAYMENT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏦</span>
      <h2>भुगतान कहाँ आता है?</h2>
    </div>
    <p>
      धान का भुगतान <strong>पंजीयन में दर्ज आपके बैंक खाते</strong> में आता है। पिछले सीज़न में खरीदी के समय समर्थन मूल्य की राशि आई, और ₹3,100 तक की बाकी अंतर राशि कृषक उन्नति योजना से बाद में एकमुश्त भेजी गई।
    </p>
    <ul>
      <li><strong>खाता चालू हो:</strong> बंद या निष्क्रिय खाते में भुगतान अटकता है।</li>
      <li><strong>नाम मेल खाए:</strong> आधार, ज़मीन के कागज़ और बैंक खाते में नाम की वर्तनी एक जैसी हो।</li>
      <li><strong>देर होने पर:</strong> तौल पर्ची लेकर अपनी सहकारी समिति या ज़िला खाद्य अधिकारी से मिलिए।</li>
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
      <li><strong>31 अक्टूबर के बाद पंजीयन की सोचना</strong> — इस साल एग्री स्टैक पंजीयन के बिना समर्थन मूल्य पर धान नहीं बिकेगा।</li>
      <li><strong>पिछले साल के पंजीयन को काफ़ी मान लेना</strong> — 2026-27 में एग्री स्टैक पर पंजीयन अलग से ज़रूरी है; समिति से पुष्टि कीजिए कि आपका हो गया है।</li>
      <li><strong>खसरा या रकबा गलत भरवाना</strong> — मात्रा रकबे से ही तय होती है।</li>
      <li><strong>गीला धान लेकर पहुँचना</strong> — 17% से ज़्यादा नमी पर धान लौटता है और टोकन का दिन बेकार जाता है।</li>
      <li><strong>टोकन के दिन से पहले या बाद में जाना</strong> — केंद्र टोकन की तारीख़ से ही चलता है।</li>
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
        <tr><td>अभी से 31 अक्टूबर तक</td><td>एग्री स्टैक पर पंजीयन — खुद या समिति से; पावती लेना</td></tr>
        <tr><td>खरीदी नीति घोषित होने पर</td><td>इस साल की दर, प्रति एकड़ सीमा और टोकन का तरीका जानना</td></tr>
        <tr><td>कटाई के बाद</td><td>सुखाई और सफ़ाई — नमी 17% से नीचे</td></tr>
        <tr><td>टोकन के दिन</td><td>समिति पर जाँच, तौल, पर्ची लेना</td></tr>
        <tr><td>बिक्री के बाद</td><td>बैंक खाते में भुगतान देखना; न आए तो समिति से संपर्क</td></tr>
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
      इस साल का सबसे ज़रूरी काम एक ही है: <strong>31 अक्टूबर से पहले एग्री स्टैक पर पंजीयन</strong>। खरीदी की तारीख़ें, राज्य की दर और टोकन का तरीका सरकार जल्द घोषित करेगी — पर वह सब पंजीयन के बाद ही आपके काम आएगा। धान सुखाकर रखिए, पावती सँभालिए, और घोषणा के लिए अपनी समिति के संपर्क में रहिए।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        यह लेख सामान्य जानकारी के लिए है। समर्थन मूल्य, राज्य की दर, तारीख़ें और पंजीयन के नियम सरकार की धान खरीदी नीति से तय होते हैं और बदलते रहते हैं। KrashiMitra न सरकारी एजेंट है, न किसी का पंजीयन करता है, न फसल खरीदता या बिकवाता है — अंतिम पुष्टि हमेशा अपनी सहकारी समिति या ज़िला खाद्य अधिकारी से ही कीजिए।
      </div>
    </div>
  </section>
"""

FAQS = [
    ("छत्तीसगढ़ में धान बेचने के लिए 2026-27 में कौन-सा पंजीयन ज़रूरी है?",
     "खरीफ विपणन वर्ष 2026-27 में समर्थन मूल्य पर धान बेचने के लिए <strong>केंद्र सरकार के एग्री स्टैक पोर्टल पर पंजीयन अनिवार्य</strong> है, और इसकी अंतिम तिथि <strong>31 अक्टूबर</strong> है। पंजीयन खुद पोर्टल पर या अपनी सहकारी समिति से कराया जा सकता है।"),
    ("छत्तीसगढ़ में धान खरीदी 2026-27 कब से शुरू होगी?",
     "28 सितंबर 2026 तक सरकार ने 2026-27 की <strong>खरीदी की तारीख़ घोषित नहीं की है</strong>। पिछले साल (2025-26) खरीदी 15 नवंबर 2025 से 31 जनवरी 2026 तक चली थी; इस साल की तारीख़ के लिए अपनी समिति से संपर्क में रहिए।"),
    ("धान का समर्थन मूल्य 2026-27 कितना है?",
     "केंद्र सरकार ने खरीफ विपणन वर्ष 2026-27 के लिए धान का समर्थन मूल्य <strong>सामान्य ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल</strong> तय किया है। छत्तीसगढ़ की अपनी दर इससे अलग होती है और 2026-27 के लिए अभी घोषित नहीं हुई है।"),
    ("छत्तीसगढ़ में ₹3,100 प्रति क्विंटल कैसे मिलता है?",
     "खरीफ विपणन वर्ष 2025-26 में राज्य मंत्रिमंडल ने धान <strong>₹3,100 प्रति क्विंटल</strong> की दर से खरीदने का फ़ैसला किया था — खरीदी के समय समर्थन मूल्य मिला और बाकी अंतर राशि कृषक उन्नति योजना से बाद में एकमुश्त खातों में आई। 2026-27 की दर सरकार की नई धान खरीदी नीति से तय होगी।"),
    ("एक एकड़ में कितना धान बिकता है?",
     "खरीफ विपणन वर्ष 2025-26 में छत्तीसगढ़ में <strong>एक एकड़ की उपज में से अधिकतम 21 क्विंटल</strong> धान खरीदा गया। 2026-27 की सीमा खरीदी नीति में घोषित होगी।"),
    ("धान बेचने का टोकन कैसे मिलता है?",
     "2025-26 में किसान <strong>टोकन तुंहर हाथ</strong> मोबाइल ऐप से ऑनलाइन टोकन ले रहे थे, और जनवरी 2026 से समिति से ऑफ़लाइन टोकन की सुविधा भी शुरू हुई। 2026-27 का तरीका खरीदी नीति में घोषित होगा, पर टोकन के लिए पंजीयन पहले ज़रूरी है।"),
    ("धान में कितनी नमी चलती है?",
     "सरकारी खरीदी में धान की अधिकतम नमी <strong>17%</strong> है। इसके अलावा अकार्बनिक और कार्बनिक अपद्रव्य 1%-1%, क्षतिग्रस्त दाने 5% और अपरिपक्व दाने 3% तक ही मान्य हैं।"),
]

ARTICLE = {
    "slug": "chhattisgarh-dhan-kharidi",
    "date": "2026-09-28",
    "date_label": "सितंबर 2026",
    "read_time": 8,
    "word_count": 1900,
    "lang": "hi",

    "section": "सरकारी योजना",
    "cat_label": "सरकारी योजना",
    "cat_query": "jankari",
    "breadcrumb_leaf": "छत्तीसगढ़ धान खरीदी",

    "title": "छत्तीसगढ़ धान खरीदी 2026-27: एग्री स्टैक पंजीयन 31 अक्टूबर तक ज़रूरी",
    "description": "2026-27 में समर्थन मूल्य पर धान बेचने के लिए एग्री स्टैक पंजीयन अनिवार्य, अंतिम तिथि 31 अक्टूबर। MSP ₹2,441, समिति में पंजीयन, टोकन और नमी 17% — पूरी जानकारी।",
    "keywords": "छत्तीसगढ़ धान खरीदी 2026-27, cg dhan kharidi 2026, chhattisgarh dhan kharidi, एग्री स्टैक पंजीयन, agri stack registration chhattisgarh, टोकन तुंहर हाथ, धान 3100 प्रति क्विंटल, कृषक उन्नति योजना, 21 क्विंटल धान खरीदी सीमा, chhattisgarh paddy procurement",

    "og_title": "छत्तीसगढ़ धान खरीदी 2026-27: एग्री स्टैक पंजीयन 31 अक्टूबर तक ज़रूरी",
    "og_desc": "समर्थन मूल्य पर धान बेचने के लिए एग्री स्टैक पंजीयन अनिवार्य, अंतिम तिथि 31 अक्टूबर। पंजीयन, टोकन और नमी 17% — पूरी जानकारी।",
    "hero_image": ("images/articles/chhattisgarh-dhan-kharidi.webp",
                   "छत्तीसगढ़ के रायगढ़ में धान का खेत",
                   "छत्तीसगढ़ के रायगढ़ का एक धान का खेत — यही फसल समिति के उपार्जन केंद्र पर बिकती है। (उपार्जन केंद्र की कोई स्वतंत्र-लाइसेंस वाली तस्वीर उपलब्ध नहीं है।)"),
    "headline": "छत्तीसगढ़ धान खरीदी 2026-27 — एग्री स्टैक पंजीयन, टोकन और भुगतान",
    "headline_en": "Chhattisgarh Paddy Procurement 2026-27 — Agri Stack Registration, Token &amp; Payment",
    "schema_desc": "छत्तीसगढ़ में 2026-27 में समर्थन मूल्य पर धान बेचने के लिए एग्री स्टैक पंजीयन (अंतिम तिथि 31 अक्टूबर), केंद्र का समर्थन मूल्य, पिछले साल की राज्य दर और सीमा, टोकन व्यवस्था, उपार्जन केंद्र पर नमी व गुणवत्ता मानक और भुगतान की जानकारी।",
    "schema_keywords": ["छत्तीसगढ़ धान खरीदी", "Chhattisgarh paddy procurement", "Agri Stack",
                        "MSP", "समर्थन मूल्य", "टोकन", "छत्तीसगढ़"],

    "h1": "छत्तीसगढ़ धान खरीदी 2026-27",
    "h1_en": "Selling Paddy at MSP in Chhattisgarh — Agri Stack, Token &amp; Payment",
    "share_title": "छत्तीसगढ़ धान खरीदी 2026-27 — एग्री स्टैक पंजीयन 31 अक्टूबर तक ज़रूरी",
    "hero_excerpt": "इस साल एक नियम बदला है: एग्री स्टैक पर पंजीयन के बिना समर्थन मूल्य पर धान नहीं बिकेगा। अंतिम तिथि 31 अक्टूबर।",
    "lede_h2": "टोकन से पहले पंजीयन, और पंजीयन की आख़िरी तारीख़ 31 अक्टूबर",

    "badges": [("badge-location", "📍 छत्तीसगढ़"),
               ("badge-season", "🗓️ पंजीयन: 31 अक्टूबर तक"),
               ("badge-disease", "🧾 एग्री स्टैक अनिवार्य")],

    "quick_facts": [("", "💰", "₹2,441", "केंद्र का MSP 2026-27, प्रति क्विंटल"),
                    ("warn", "📅", "31 अक्टूबर", "एग्री स्टैक पंजीयन की अंतिम तिथि"),
                    ("danger", "💧", "17%", "इससे ऊपर नमी तो धान नहीं तुलता")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-common", "धान का भाव"),
                   ("maize", "मक्का का भाव"),
                   ("wheat", "गेहूं का भाव")],

    "card": {
        "emoji": "🧾", "bg": "#eff6ff", "accent": "#0369a1",
        "tag": "छत्तीसगढ़ धान खरीदी", "tag_bg": "#dbeafe", "tag_color": "#0369a1",
        "title": "छत्तीसगढ़ धान खरीदी 2026-27 — एग्री स्टैक पंजीयन, टोकन और भुगतान",
        "cats": "jankari",
        "keywords": "छत्तीसगढ़ धान खरीदी cg dhan kharidi agri stack एग्री स्टैक पंजीयन टोकन तुंहर हाथ 3100 कृषक उन्नति योजना 21 क्विंटल समिति MSP 2441",
    },

    "related": [
        (f"{SITE}/articles/bihar-dhan-adhiprapti", "#0369a1", "🧾", "बिहार · धान अधिप्राप्ति",
         "बिहार धान अधिप्राप्ति 2026-27 — PACS में धान बेचने का पंजीकरण"),
        (f"{SITE}/articles/mp-e-uparjan-panjiyan", "#0369a1", "🧾", "MP · उपार्जन",
         "MP ई-उपार्जन पंजीयन — समर्थन मूल्य पर फसल कैसे बेचें"),
        (f"{SITE}/articles/up-dhan-kharid-panjikaran", "#0369a1", "🧾", "UP · धान खरीद",
         "UP धान खरीद पंजीकरण — MSP ₹2,441 पर धान बेचने की पूरी प्रक्रिया"),
        (f"{SITE}/articles/dhan-nami-mandi-rejection", "#0f766e", "💧", "धान · गुणवत्ता",
         "धान में नमी कितनी होनी चाहिए? 17% का पूरा नियम"),
        (f"{SITE}/bhav/paddy-common", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "धान का आज का मंडी भाव — राज्यवार LIVE रेट"),
    ],
}
