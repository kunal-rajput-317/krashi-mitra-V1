# -*- coding: utf-8 -*-
# ============================================================
# बासमती धान की किस्में — 1509, 1692, 1718, 1121 (+ 1847, 1885, 1886).
# Written 6 Oct 2026.
#
# Why: Search Console (7 Sep – 4 Oct 2026) shows farmers searching basmati by
# VARIETY NUMBER — "1692 dhan ka rate today aligarh", "1509 dhan ka rate today
# karnal", "1718 dhan ka rate" — thousands of impressions landing on /bhav
# district pages at ~1% CTR. The site had zero content on any basmati variety.
# Agmarknet reports "Paddy Basmati" without the variety, so this page explains
# the varieties and sends the reader to the live mandi pages; it never prints
# a variety-wise price it cannot source.
#
# Sources (read 5–6 Oct 2026):
#   • PB 1121: released 2003 as Pusa Sugandh 4, notified S.O. 1566(E)
#     5 Nov 2005; raw grain up to ~9 mm, cooked 21.5 mm; ~70% of basmati export
#     share; 19–20 q paddy per acre vs 9–10 for traditional basmati —
#     Wikipedia "Pusa Basmati 1121" (citing IARI). 140–145 days seed to seed —
#     Rice journal (Springer) 10.1186/s12284-018-0213-6. ICAR calls it the
#     "highest forex earner" — icar.org.in basmati varieties page.
#   • PB 1509: notified S.O. 2815(E) 19 Sep 2013, cross PB 1121 × Pusa 1301;
#     matures in 115 days, average 41.4 q/ha — ICAR page; non-lodging,
#     non-shattering — krishi.icar.gov.in. Bakanae incidence especially high
#     on PB 1121 and PB 1509 — ICAR journal (JWR / IJAS).
#   • PB 1692: derived from PB 1509 by pedigree breeding at IARI; 110–115 days
#     seed to seed; 20–24 q per acre; semi-dwarf, non-lodging, non-shattering —
#     Global Agriculture (IARI release coverage).
#   • PB 1718: near-isogenic line of PB 1121 with BLB genes xa13 + Xa21;
#     notified 25 Aug 2017 for Punjab, Haryana, Delhi; 136–138 days; average
#     46.4 q/ha — ICAR page; Springer Rice journal.
#   • PB 1847 (improved PB 1509, BLB xa13 + Xa21, blast Pi54 + Pi2, ~125 days,
#     5.7 t/ha, released 2021), PB 1885 (PB 1121 + BLB & blast resistance,
#     135–140 days), PB 1886 (PB 1401 + BLB & blast resistance) — IARI via
#     Agrospectrum / Vajiram / APEDA "Newly released basmati varieties".
#   • GI area: Punjab, Haryana, Delhi, Himachal Pradesh, Uttarakhand, western
#     UP and parts of J&K — APEDA GI, as reported in the MP GI dispute coverage.
#   • Basmati not procured at MSP (not part of PDS) — Tribune.
#
# Deliberately NOT claimed: any variety-wise mandi price or which variety
# "pays more", sowing/transplanting dates, any pesticide name or dose
# (LEGAL_RULES §2), the release year of PB 1692, PB 1886's exact duration.
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
      मंडी में बासमती का भाव पूछा जाए तो किसान "बासमती" नहीं कहता — वह कहता है <strong>"1509 का क्या रेट है?"</strong>, <strong>"1692 कितने में बिका?"</strong>, <strong>"1121 और 1718 में कितना फ़र्क है?"</strong> ये नंबर असल में भारतीय कृषि अनुसंधान संस्थान (IARI, पूसा) की बनाई <strong>पूसा बासमती</strong> किस्मों के नाम हैं।
    </p>
    <p>
      हर किस्म का दाना, पकने का समय, उपज और रोग से लड़ने की ताक़त अलग है — और इसी से उसकी बोली भी अलग लगती है। इस लेख में सभी बड़ी किस्मों का फ़र्क एक तालिका में है, बासमती MSP पर क्यों नहीं बिकता, और मंडी में अपनी किस्म का सही भाव पाने के लिए क्या ध्यान रखें।
    </p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>आज का भाव कहाँ देखें:</strong> सरकारी मंडी रिपोर्ट में बासमती ज़्यादातर "धान बासमती" नाम से दर्ज होता है, किस्म के नंबर के साथ नहीं। अपनी मंडी का ताज़ा भाव <a href="https://krashimitra.in/bhav/paddy-basmati">बासमती धान का आज का मंडी भाव</a> पर देखिए — <a href="https://krashimitra.in/bhav/paddy-basmati/haryana/karnal">करनाल</a>, <a href="https://krashimitra.in/bhav/paddy-basmati/uttar-pradesh/mathura">मथुरा</a>, <a href="https://krashimitra.in/bhav/paddy-basmati/punjab">पंजाब</a>।
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

  <!-- THE TABLE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📊</span>
      <h2>सभी बड़ी बासमती किस्में — एक तालिका में</h2>
    </div>
    <p>
      "पकने का समय" बीज बोने से फसल तैयार होने तक का है (बीज से बीज)। उपज औसत है — आपके खेत की मिट्टी, पानी और देखभाल से यह ऊपर-नीचे होती है।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>किस्म</th><th>पकने में</th><th>औसत उपज</th><th>पहचान</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>पूसा बासमती 1121</strong></td><td>140–145 दिन</td><td>एक एकड़ में 19–20 क्विंटल</td><td>सबसे लंबा दाना; निर्यात की सबसे बड़ी किस्म</td></tr>
        <tr><td><strong>पूसा बासमती 1718</strong></td><td>136–138 दिन</td><td>एक हेक्टेयर में औसत 46.4 क्विंटल</td><td>1121 जैसा दाना, साथ में झुलसा (BLB) रोग से बचाव</td></tr>
        <tr><td><strong>पूसा बासमती 1509</strong></td><td>115–120 दिन</td><td>एक हेक्टेयर में औसत 41.4 क्विंटल</td><td>जल्दी पकने वाली; गिरती नहीं, दाना झड़ता नहीं</td></tr>
        <tr><td><strong>पूसा बासमती 1692</strong></td><td>110–115 दिन</td><td>एक एकड़ में 20–24 क्विंटल</td><td>1509 से बनी; सबसे जल्दी पकने वाली में से</td></tr>
        <tr><td><strong>पूसा बासमती 1847</strong></td><td>लगभग 125 दिन</td><td>एक हेक्टेयर में औसत 57 क्विंटल</td><td>1509 का सुधरा रूप — झुलसा और झोंका दोनों से बचाव</td></tr>
        <tr><td><strong>पूसा बासमती 1885</strong></td><td>135–140 दिन</td><td>—</td><td>1121 का सुधरा रूप — झुलसा और झोंका से बचाव</td></tr>
        <tr><td><strong>पूसा बासमती 1886</strong></td><td>देर से पकने वाली</td><td>—</td><td>1401 का सुधरा रूप — झुलसा और झोंका से बचाव</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        ये आँकड़े ICAR-IARI और उसकी प्रकाशित रिपोर्टों के औसत हैं, किसी खेत की गारंटी नहीं। आपके ज़िले के लिए कौन-सी किस्म सबसे ठीक है, यह अपने <strong>कृषि विज्ञान केंद्र (KVK)</strong> या ज़िला कृषि अधिकारी से ज़रूर पूछिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- 1121 -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🌾</span>
      <h2>1121 धान — सबसे लंबा दाना</h2>
    </div>
    <p>
      पूसा बासमती 1121 को <strong>2003 में खेती के लिए जारी</strong> किया गया था (पहले नाम "पूसा सुगंध 4")। इसका कच्चा दाना लगभग <strong>9 मिलीमीटर</strong> तक लंबा होता है और पकने पर <strong>21.5 मिलीमीटर</strong> तक बढ़ जाता है — यही लंबाई इसे विदेशी बाज़ार में पसंद कराती है। भारत के बासमती निर्यात का सबसे बड़ा हिस्सा इसी किस्म का रहा है, और ICAR इसे सबसे ज़्यादा विदेशी मुद्रा कमाने वाली किस्म कहता है।
    </p>
    <ul>
      <li><strong>पकने में:</strong> 140–145 दिन — यानी खेत लंबे समय तक घिरा रहता है।</li>
      <li><strong>उपज:</strong> एक एकड़ में 19–20 क्विंटल धान, जबकि पुरानी देसी बासमती में 9–10 क्विंटल होता था।</li>
      <li><strong>कमज़ोरी:</strong> झुलसा (BLB) और बकाने (पौधा लंबा-पीला होकर सूखना) रोग का असर ज़्यादा।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- 1718 -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🛡️</span>
      <h2>1718 धान — 1121 जैसा, पर झुलसा रोग से बचाव के साथ</h2>
    </div>
    <p>
      पूसा बासमती 1718 असल में <strong>1121 का ही सुधरा रूप</strong> है। IARI ने 1121 में जीवाणु झुलसा (बैक्टीरियल लीफ ब्लाइट) से लड़ने वाले दो जीन (xa13 और Xa21) डाले। इसे <strong>25 अगस्त 2017</strong> को पंजाब, हरियाणा और दिल्ली के लिए अधिसूचित किया गया।
    </p>
    <ul>
      <li><strong>पकने में:</strong> 136–138 दिन, लगभग 1121 जितना।</li>
      <li><strong>उपज:</strong> एक हेक्टेयर में औसत 46.4 क्विंटल।</li>
      <li><strong>फ़ायदा:</strong> झुलसा रोग पर दवा का ख़र्च और जोखिम दोनों घटते हैं — शोध में इस पर एंटीबायोटिक छिड़काव की ज़रूरत काफ़ी कम पाई गई।</li>
    </ul>
    <p>
      झुलसा रोग पहचानने का तरीका <a href="https://krashimitra.in/articles/dhan-jivanu-jhulsa-blb">धान का जीवाणु झुलसा (BLB)</a> में है।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- 1509 -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">⏱️</span>
      <h2>1509 धान — जल्दी पकने वाली</h2>
    </div>
    <p>
      पूसा बासमती 1509 को <strong>19 सितंबर 2013</strong> को अधिसूचित किया गया। यह 1121 और पूसा 1301 के मेल से बनी है, और इसका सबसे बड़ा गुण है समय — यह लगभग <strong>115–120 दिन</strong> में पक जाती है, यानी 1121 से 3–4 हफ़्ते पहले।
    </p>
    <ul>
      <li><strong>उपज:</strong> एक हेक्टेयर में औसत 41.4 क्विंटल।</li>
      <li><strong>पौधा:</strong> गिरता नहीं (लॉजिंग नहीं) और पके दाने झड़ते नहीं।</li>
      <li><strong>जल्दी खाली खेत:</strong> धान जल्दी कटता है, तो गेहूं की बुवाई और पराली संभालने के लिए ज़्यादा समय मिलता है।</li>
      <li><strong>कमज़ोरी:</strong> 1121 की तरह इसमें भी बकाने और झुलसा रोग का असर ज़्यादा देखा गया है।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 2 ── -->
  <div class="ad-slot responsive" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="4489195916" data-format="auto"></div>
    </div>
  </div>

  <!-- 1692 -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚀</span>
      <h2>1692 धान — 1509 से भी जल्दी</h2>
    </div>
    <p>
      पूसा बासमती 1692 को IARI के वैज्ञानिकों ने <strong>1509 से ही विकसित</strong> किया है। यह बीज से बीज तक लगभग <strong>110–115 दिन</strong> में तैयार हो जाती है — बासमती की सबसे जल्दी पकने वाली किस्मों में से एक।
    </p>
    <ul>
      <li><strong>उपज:</strong> एक एकड़ में औसतन 20–24 क्विंटल।</li>
      <li><strong>पौधा:</strong> मध्यम-बौना, गिरता नहीं, दाना झड़ता नहीं।</li>
      <li><strong>किसके लिए:</strong> जिन्हें धान के बाद समय पर गेहूं या आलू बोना है, या जहाँ पानी कम है — कम दिन खेत में रहने से सिंचाई भी कम लगती है।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- NEW RESISTANT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧬</span>
      <h2>नई रोग-रोधी किस्में — 1847, 1885, 1886</h2>
    </div>
    <p>
      2021 में IARI ने तीन नई किस्में जारी कीं, जो पुरानी लोकप्रिय किस्मों के ही सुधरे रूप हैं — दाना और पकने का समय वही, पर <strong>झुलसा (BLB) और झोंका (ब्लास्ट)</strong> दोनों रोगों से बचाव के जीन के साथ:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>नई किस्म</th><th>किसका सुधरा रूप</th><th>किसकी जगह सोचें</th></tr>
      </thead>
      <tbody>
        <tr><td>पूसा बासमती 1847</td><td>1509</td><td>जो किसान 1509 बोते हैं</td></tr>
        <tr><td>पूसा बासमती 1885</td><td>1121</td><td>जो किसान 1121 बोते हैं</td></tr>
        <tr><td>पूसा बासमती 1886</td><td>1401</td><td>जो किसान 1401 बोते हैं</td></tr>
      </tbody>
    </table>
    <p>
      बासमती निर्यात में कीटनाशक अवशेष (MRL) की जाँच बहुत सख़्त होती है। रोग-रोधी किस्म से छिड़काव की ज़रूरत घटती है, और इसी से विदेश जाने वाले माल के लौटने का खतरा भी कम होता है। झोंका रोग की पहचान <a href="https://krashimitra.in/articles/dhan-jhonka-rog">धान का झोंका रोग</a> में है।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- COMPARISON -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">⚖️</span>
      <h2>जल्दी वाली बनाम लंबी अवधि वाली — कौन-सी किसके लिए</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>बिंदु</th><th>1509 / 1692 / 1847</th><th>1121 / 1718 / 1885</th></tr>
      </thead>
      <tbody>
        <tr><td>पकने में</td><td class="healthy">110–125 दिन</td><td class="diseased">135–145 दिन</td></tr>
        <tr><td>सिंचाई</td><td class="healthy">कम दिन, कम पानी</td><td class="diseased">ज़्यादा दिन खेत में</td></tr>
        <tr><td>अगली फसल</td><td class="healthy">गेहूं-आलू के लिए समय बचता है</td><td class="diseased">अगली बुवाई में देर का खतरा</td></tr>
        <tr><td>दाने की लंबाई</td><td class="diseased">लंबा, पर 1121 से कम</td><td class="healthy">सबसे लंबा दाना</td></tr>
        <tr><td>मंडी में आवक</td><td>पहले पहुँचती है</td><td>बाद में पहुँचती है</td></tr>
      </tbody>
    </table>
    <p>
      कोई एक किस्म "सबसे अच्छी" नहीं है। फ़ैसला आपके खेत के पानी, अगली फसल और आसपास के खरीदारों की माँग से होता है — अपने इलाक़े के आढ़ती और KVK दोनों से पूछकर तय कीजिए।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- NO MSP -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏷️</span>
      <h2>बासमती का सरकारी रेट (MSP) क्यों नहीं होता?</h2>
    </div>
    <p>
      <strong>बासमती धान समर्थन मूल्य पर नहीं खरीदा जाता।</strong> सरकारी खरीद का धान राशन (PDS) के चावल में जाता है, और बासमती उसमें शामिल नहीं है। इसलिए बासमती मंडी में <strong>खुली बोली</strong> पर निजी व्यापारी, चावल मिलें और निर्यातक खरीदते हैं।
    </p>
    <p>
      इसका मतलब है कि बासमती का भाव रोज़ बदलता है — विदेश की माँग, नई फसल की आवक, किस्म और दाने की गुणवत्ता, सब इस पर असर डालते हैं। सामान्य धान का सरकारी रेट कितना है, यह <a href="https://krashimitra.in/articles/dhan-msp-sarkari-rate-2026-27">धान का सरकारी रेट 2026-27</a> में है।
    </p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>भौगोलिक संकेतक (GI):</strong> "बासमती" नाम का GI टैग पंजाब, हरियाणा, दिल्ली, हिमाचल प्रदेश, उत्तराखंड, पश्चिमी उत्तर प्रदेश और जम्मू-कश्मीर के कुछ हिस्सों के लिए है। निर्यात में "बासमती" नाम से बिकने वाला चावल इसी इलाक़े का होना चाहिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- AT THE MANDI -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏪</span>
      <h2>मंडी में अपनी किस्म का पूरा भाव कैसे पाएँ</h2>
    </div>
    <ul>
      <li><strong>किस्में अलग-अलग रखिए:</strong> व्यापारी हर किस्म की अलग बोली लगाते हैं। 1509 और 1121 एक ढेरी में मिलाए, तो पूरी ढेरी का भाव कम वाली किस्म के हिसाब से लग सकता है।</li>
      <li><strong>सुखाकर लाइए:</strong> गीले धान पर बोली कम लगती है और कटौती होती है। सुखाने का तरीका <a href="https://krashimitra.in/articles/dhan-nami-mandi-rejection">धान में नमी का नियम</a> में है।</li>
      <li><strong>साफ़ धान:</strong> पुआल, मिट्टी और कच्चे दाने अलग कर लीजिए — टूटा या बदरंग दाना पूरे लॉट का भाव गिराता है।</li>
      <li><strong>एक से ज़्यादा बोली देखिए:</strong> बेचने से पहले आसपास की दो-तीन मंडियों का भाव देख लीजिए।</li>
      <li><strong>पर्ची लीजिए:</strong> हरियाणा-पंजाब की मंडियों में बिक्री की पर्ची (J-फॉर्म) ज़रूर लीजिए — भाव, वज़न और भुगतान का यही सबूत है।</li>
    </ul>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        KrashiMitra किसी को बेचने या रोकने की सलाह नहीं देता। मंडी भाव सरकारी रिपोर्ट से लिए जाते हैं और सिर्फ़ जानकारी के लिए हैं — बेचने का फ़ैसला अपनी ज़रूरत और स्थानीय बोली देखकर खुद कीजिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- MISTAKES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚫</span>
      <h2>ये गलतियाँ न करें</h2>
    </div>
    <ul>
      <li><strong>बिना बिल का "1121" या "1509" बीज खरीदना:</strong> नकली या मिलावटी बीज की शिकायत आम है। बीज IARI, राज्य कृषि विश्वविद्यालय, कृषि विभाग या लाइसेंसी दुकान से, पक्के बिल के साथ लीजिए।</li>
      <li><strong>किस्में मिलाकर बेचना:</strong> मिली-जुली ढेरी का भाव अच्छी किस्म के हिसाब से नहीं लगता।</li>
      <li><strong>बासमती को MSP की लाइन में लगाना:</strong> सरकारी केंद्र बासमती नहीं खरीदते।</li>
      <li><strong>बिना पूछे कोई भी दवा छिड़कना:</strong> निर्यात वाले बासमती में रसायन अवशेष की जाँच होती है, और कुछ राज्य कुछ कीटनाशकों पर बासमती में रोक लगा चुके हैं। छिड़काव से पहले ज़िला कृषि अधिकारी या KVK से पूछिए।</li>
      <li><strong>बकाने रोग वाले पौधे खेत में छोड़ देना:</strong> लंबे, पीले, पतले पौधे दिखें तो उखाड़कर खेत से बाहर कर दीजिए, और अगली बार बीज उपचार के बारे में KVK से पूछिए।</li>
      <li><strong>पराली जलाना:</strong> जल्दी पकने वाली किस्म का फ़ायदा यही है कि पराली संभालने का समय मिलता है — <a href="https://krashimitra.in/articles/parali-prabandhan">पराली प्रबंधन</a> देखिए।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CALENDAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>कटाई से बिक्री तक — पूरा क्रम</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>समय</th><th>ज़रूरी काम</th></tr></thead>
      <tbody>
        <tr><td>कटाई से 1-2 हफ़्ते पहले</td><td>आसपास की मंडियों का बासमती भाव देखना; खरीदार और आढ़ती से बात</td></tr>
        <tr><td>कटाई</td><td>हर किस्म अलग काटना और अलग ढेरी रखना</td></tr>
        <tr><td>कटाई के बाद</td><td>धूप में सुखाना, साफ़ करना, कच्चे-टूटे दाने अलग करना</td></tr>
        <tr><td>मंडी में</td><td>किस्म का नाम बताकर बोली; तौल देखना; पर्ची / J-फॉर्म लेना</td></tr>
        <tr><td>बिक्री के बाद</td><td>भुगतान का मिलान; अगली बार के लिए किस्म की उपज और भाव लिखकर रखना</td></tr>
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
      <strong>1509 और 1692</strong> जल्दी पकती हैं और खेत जल्दी खाली करती हैं; <strong>1121</strong> सबसे लंबा दाना देती है पर ज़्यादा दिन लेती है; <strong>1718</strong> 1121 जैसी है पर झुलसा रोग से बची रहती है; और <strong>1847, 1885, 1886</strong> पुरानी किस्मों के रोग-रोधी रूप हैं। बासमती MSP पर नहीं बिकता, इसलिए किस्म अलग रखना, सुखाकर लाना और भाव देखकर बेचना ही पूरा दाम दिलाता है।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        यह लेख सामान्य जानकारी के लिए है। किस्मों के आँकड़े ICAR-IARI के प्रकाशित औसत हैं; आपकी उपज मिट्टी, पानी, मौसम और देखभाल पर टिकी है। बीज और दवा का चुनाव अपने KVK या ज़िला कृषि अधिकारी की सलाह से कीजिए। KrashiMitra एक निजी वेबसाइट है और किसी की फसल खरीदता या बिकवाता नहीं।
      </div>
    </div>
  </section>
"""

FAQS = [
    ("1509 धान कितने दिन में पकता है?",
     "पूसा बासमती 1509 लगभग <strong>115–120 दिन</strong> में पकता है, यानी 1121 से 3–4 हफ़्ते पहले। इसका औसत उत्पादन एक हेक्टेयर में 41.4 क्विंटल है।"),
    ("1692 धान कितने दिन की फसल है?",
     "पूसा बासमती 1692 बीज से बीज तक लगभग <strong>110–115 दिन</strong> की फसल है। यह 1509 से विकसित की गई है और एक एकड़ में औसतन 20–24 क्विंटल उपज देती है।"),
    ("1121 और 1718 धान में क्या फ़र्क है?",
     "1718 असल में <strong>1121 का सुधरा रूप है, जिसमें जीवाणु झुलसा (BLB) रोग से बचाव के दो जीन डाले गए हैं</strong>। दाना और पकने का समय लगभग एक जैसा है — 1121 को 140–145 दिन और 1718 को 136–138 दिन लगते हैं।"),
    ("1692 धान का रेट आज कितना है?",
     "सरकारी मंडी रिपोर्ट में बासमती <strong>किस्म के नंबर के बिना \"धान बासमती\" नाम से</strong> दर्ज होता है, इसलिए 1692 का अलग सरकारी भाव नहीं छपता। अपनी मंडी का ताज़ा बासमती भाव KrashiMitra के बासमती मंडी भाव पेज पर देखिए और किस्म का भाव आढ़ती से पूछिए।"),
    ("क्या बासमती धान MSP पर बिकता है?",
     "<strong>नहीं — बासमती धान समर्थन मूल्य पर नहीं खरीदा जाता।</strong> वह मंडी में खुली बोली पर निजी व्यापारी और निर्यातक खरीदते हैं, इसलिए उसका भाव रोज़ बदलता है।"),
    ("सबसे जल्दी पकने वाली बासमती किस्म कौन-सी है?",
     "<strong>पूसा बासमती 1692 (110–115 दिन) और 1509 (115–120 दिन)</strong> सबसे जल्दी पकने वाली बासमती किस्मों में हैं। 1509 का रोग-रोधी रूप पूसा बासमती 1847 लगभग 125 दिन लेता है।"),
    ("झुलसा रोग से बचाव वाली बासमती किस्म कौन-सी है?",
     "<strong>पूसा बासमती 1718</strong> में झुलसा (BLB) से बचाव है, और <strong>1847, 1885 और 1886</strong> में झुलसा और झोंका दोनों से बचाव है। ये क्रमशः 1121, 1509, 1121 और 1401 के सुधरे रूप हैं।"),
    ("1121 धान का दाना कितना लंबा होता है?",
     "पूसा बासमती 1121 का कच्चा दाना लगभग <strong>9 मिलीमीटर</strong> तक लंबा होता है और पकने पर <strong>21.5 मिलीमीटर</strong> तक बढ़ जाता है। इसी लंबाई की वजह से यह निर्यात की सबसे बड़ी बासमती किस्म है।"),
]

ARTICLE = {
    "slug": "basmati-dhan-kisme-1509-1692-1718",
    "date": "2026-10-06",
    "date_label": "अक्टूबर 2026",
    "read_time": 9,
    "word_count": 2100,
    "lang": "hi",

    "section": "फसल गाइड",
    "cat_label": "फसल गाइड",
    "cat_query": "anaaj",
    "breadcrumb_leaf": "बासमती किस्में",

    "title": "1509, 1692, 1718, 1121 Dhan: बासमती किस्मों का फ़र्क और आज का भाव",
    "description": "1692 (110–115 दिन) और 1509 (115–120 दिन) सबसे जल्दी, 1121 व 1718 (136–145 दिन) देर से पकते हैं। 1718 में झुलसा से बचाव। बासमती MSP पर नहीं बिकता — भाव कहाँ देखें।",
    "keywords": "1509 dhan, 1692 dhan, 1718 dhan, 1121 dhan, पूसा बासमती 1509, पूसा बासमती 1692, बासमती धान की किस्में, basmati dhan ki variety, 1692 dhan kitne din me pakta hai, 1509 dhan ka rate, pusa basmati 1718, pusa basmati 1847 1885 1886",

    "og_title": "1509, 1692, 1718, 1121 धान — बासमती किस्मों का पूरा फ़र्क | KrashiMitra.in",
    "og_desc": "कौन-सी बासमती कितने दिन में पकती है, कितनी उपज देती है, किसमें रोग से बचाव है — और मंडी भाव कहाँ देखें।",
    "hero_image": ("images/articles/basmati-dhan-kisme-1509-1692-1718.webp",
                   "पंजाब के कलानौर में कटी हुई बासमती धान की पूलियाँ खेत में पड़ी हैं",
                   "कलानौर (गुरदासपुर, पंजाब) में बासमती धान की कटाई — बासमती के GI इलाक़े का एक खेत।"),
    "headline": "1509, 1692, 1718, 1121 धान — बासमती किस्मों का पूरा फ़र्क",
    "headline_en": "Pusa Basmati 1509, 1692, 1718, 1121 — how the varieties differ",
    "schema_desc": "पूसा बासमती 1121, 1718, 1509, 1692, 1847, 1885 और 1886 — पकने का समय, औसत उपज, रोग से बचाव और दाने का फ़र्क; बासमती MSP पर क्यों नहीं बिकता और मंडी में किस्म का पूरा भाव पाने के तरीके।",
    "schema_keywords": ["पूसा बासमती 1509", "पूसा बासमती 1692", "पूसा बासमती 1718",
                        "पूसा बासमती 1121", "basmati varieties"],

    "h1": "1509, 1692, 1718, 1121 — बासमती धान की किस्में",
    "h1_en": "Pusa Basmati Varieties — 1509, 1692, 1718, 1121 and the New Resistant Ones",
    "share_title": "1509, 1692, 1718, 1121 धान — कौन-सी बासमती कितने दिन में पकती है और किसमें रोग से बचाव",
    "hero_excerpt": "1692 और 1509 सबसे जल्दी पकती हैं, 1121 सबसे लंबा दाना देती है, 1718 झुलसा से बची रहती है — और बासमती MSP पर नहीं बिकता।",
    "lede_h2": "नंबर से पहचानी जाने वाली किस्में",

    "badges": [("badge-location", "📍 पंजाब · हरियाणा · पश्चिमी UP"),
               ("badge-season", "🗓️ खरीफ · कटाई सितंबर – नवंबर"),
               ("badge-disease", "🌾 MSP पर नहीं, खुली बोली पर")],

    "quick_facts": [("", "⏱️", "110–115 दिन", "1692 — सबसे जल्दी पकने वाली में से"),
                    ("warn", "🌾", "21.5 मिमी", "1121 का पका दाना — सबसे लंबा"),
                    ("danger", "🏷️", "MSP नहीं", "बासमती खुली बोली पर बिकता है")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-basmati", "बासमती धान का भाव"),
                   ("paddy-common", "धान का भाव"),
                   ("rice", "चावल का भाव"),
                   ("wheat", "गेहूं का भाव")],

    "card": {
        "emoji": "🌾", "bg": "#fefce8", "accent": "#a16207",
        "tag": "बासमती किस्में", "tag_bg": "#fef9c3", "tag_color": "#a16207",
        "title": "1509, 1692, 1718, 1121 धान — बासमती किस्मों का पूरा फ़र्क",
        "cats": "anaaj",
        "keywords": "1509 1692 1718 1121 1847 1885 1886 pusa basmati dhan variety बासमती किस्म कितने दिन उपज झुलसा रोग msp मंडी भाव",
    },

    "related": [
        (f"{SITE}/articles/dhan-msp-sarkari-rate-2026-27", "#ca8a04", "🌾", "धान · MSP",
         "धान का सरकारी रेट 2026-27 — सामान्य ₹2,441, ग्रेड A ₹2,461"),
        (f"{SITE}/articles/haryana-dhan-kharid", "#0369a1", "🧾", "हरियाणा · धान",
         "हरियाणा धान खरीद 2026 — मेरी फसल मेरा ब्यौरा, गेट पास, J-फॉर्म"),
        (f"{SITE}/articles/dhan-jivanu-jhulsa-blb", "#b91c1c", "🦠", "धान · रोग",
         "धान का जीवाणु झुलसा (BLB) — पहचान और बचाव"),
        (f"{SITE}/articles/dhan-nami-mandi-rejection", "#0f766e", "💧", "धान · गुणवत्ता",
         "धान में नमी कितनी होनी चाहिए? 17% का पूरा नियम"),
        (f"{SITE}/articles/parali-prabandhan", "#a16207", "🔥", "पराली · प्रबंधन",
         "पराली प्रबंधन — जलाए बिना पुआल का सही इस्तेमाल"),
        (f"{SITE}/bhav/paddy-basmati", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "बासमती धान का आज का मंडी भाव — राज्यवार LIVE रेट"),
    ],
}
