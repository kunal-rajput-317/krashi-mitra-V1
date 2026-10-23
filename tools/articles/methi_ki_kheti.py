# -*- coding: utf-8 -*-
# ============================================================
# मेथी की खेती — बुवाई, किस्में, कटाई, रोग
#
# Why this topic (21 Oct 2026): rabi sowing window for methi is open now
# (Oct–Nov in the northern plains), the site had ZERO methi content, and both
# /bhav/methi-leaves and /bhav/methi-seeds are live — so it opens a crop
# cluster. GSC already shows methi price queries (मेथी बाजार भाव आजचे) with
# no article to link them to.
#
# Sources:
#   · TNAU Agritech, Fenugreek — varieties table (Co 1, Pusa Early Bunching,
#     Lam Selection 1, Rajendra Kranti, Hisar Sonali, RMt-1, RMt-143, Co 2 and
#     their tolerances), season (June–July and October–November), cool dry
#     frost-free climate, loamy well-drained soil, seed rate (about 12 kg of
#     seed in one hectare, line sowing), 20 × 15 cm spacing, Azospirillum + Trichoderma seed treatment,
#     greens at 20–25 days, grain at 90–100 days, root rot + powdery mildew.
#   · Vikaspedia (citing ICAR) — RMt-305: early, determinate, 120–125 days,
#     resistant to powdery mildew and root-knot nematode; Kasuri methi is a
#     late type, ~150–160 days seed to seed, tolerates frost; zone sowing
#     table (sub-tropical Sept–Nov, high hills March–April).
#   · ICAR Indian J. Seed Spices — AFg-3 and AFg-4 (NRCSS Ajmer), notified for
#     all fenugreek areas of India (S.O. 3666(E), 6 Dec 2016), moderately
#     resistant to powdery mildew and root rot.
# No yields and no doses (LEGAL_RULES §2, §3 — no income promise). Chemicals
# are named with timing only; the builder injects the label/KVK advisory.
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
      <strong>मेथी</strong> उन गिनी-चुनी फसलों में है जो दो बार कमाई देती है — पहले हरी पत्ती सब्ज़ी के रूप
      में, फिर दाना मसाले के रूप में। अक्टूबर-नवंबर में बोई मेथी की पहली पत्ती <strong>लगभग 20–25 दिन</strong>
      में तोड़ने लायक हो जाती है, यानी रबी की सबसे जल्दी नक़द देने वाली फसलों में से एक।
    </p>
    <p>
      पर मेथी में सबसे ज़्यादा नुकसान दो चीज़ों से होता है — <strong>पानी भरने से जड़ गलन</strong> और
      <strong>पत्तियों पर सफ़ेद पाउडर (छाछ्या रोग)</strong>। दोनों ज़्यादातर ग़लत समय की बुवाई और ज़्यादा
      सिंचाई से आते हैं, दवा से पहले खेत के तरीके से रुकते हैं। इस लेख में बुवाई से बिक्री तक पूरा तरीका है।
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

  <!-- TWO KINDS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔍</span>
      <h2>देसी मेथी और कसूरी मेथी — क्या फ़र्क है?</h2>
    </div>
    <p>
      बाज़ार में मेथी दो तरह की है, और दोनों की खेती अलग है। बोने से पहले तय करें कि आपको क्या बेचना है —
      हरी पत्ती, सूखी पत्ती या दाना।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>पहलू</th><th>देसी (साधारण) मेथी</th><th>कसूरी मेथी</th></tr>
      </thead>
      <tbody>
        <tr><td>वानस्पतिक नाम</td><td>Trigonella foenum-graecum</td><td>Trigonella corniculata</td></tr>
        <tr><td>बढ़वार</td><td class="healthy">तेज़ — जल्दी पत्ती</td><td>धीमी, झाड़ीदार</td></tr>
        <tr><td>पत्ती</td><td>बड़ी, हल्की कड़वी</td><td class="healthy">छोटी, तेज़ सुगंध वाली</td></tr>
        <tr><td>कटाई</td><td>पत्ती 1–2 बार, फिर दाना</td><td class="healthy">पत्ती की कई कटाई</td></tr>
        <tr><td>दाने तक</td><td>किस्म के अनुसार लगभग 90–150 दिन</td><td class="diseased">देर — लगभग 150–160 दिन</td></tr>
        <tr><td>पाला</td><td class="diseased">फूल के समय पाले से नुकसान</td><td class="healthy">पाला काफ़ी सह लेती है</td></tr>
        <tr><td>मुख्य बिक्री</td><td>हरी पत्ती और दाना (मसाला)</td><td>सुखाई हुई पत्ती (कसूरी मेथी)</td></tr>
      </tbody>
    </table>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>मेथी दलहनी फसल है।</strong> इसकी जड़ों की गाँठों में बैक्टीरिया हवा से नाइट्रोजन लेते हैं, इसलिए
        मेथी के बाद वाली फसल को खेत थोड़ा बेहतर मिलता है। यही कारण है कि मेथी को ज़्यादा नाइट्रोजन खाद की
        ज़रूरत नहीं होती — ज़्यादा यूरिया से पत्ती तो बढ़ती है, पर रोग भी बढ़ते हैं।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- SOWING TIME -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>मेथी की बुवाई कब करें?</h2>
    </div>
    <ul>
      <li><strong>उत्तर और मध्य भारत के मैदान (UP, MP, राजस्थान, हरियाणा, पंजाब, बिहार, गुजरात):</strong> अक्टूबर से नवंबर। दाने वाली फसल के लिए अक्टूबर के आख़िर से नवंबर का पहला पखवाड़ा सबसे सुरक्षित है, ताकि फूल कड़ाके के पाले से पहले या बाद में आएँ।</li>
      <li><strong>सिर्फ़ हरी पत्ती के लिए:</strong> सितंबर के आख़िर से ही बोई जा सकती है। हर 15–20 दिन पर छोटे टुकड़े में बुवाई करें, तो पूरी सर्दी मंडी में लगातार पत्ती जाती रहती है।</li>
      <li><strong>दक्षिण भारत:</strong> जून-जुलाई और अक्टूबर-नवंबर — दो मौसम।</li>
      <li><strong>ऊँचे पहाड़:</strong> मार्च-अप्रैल।</li>
    </ul>
    <p>
      मेथी को <strong>ठंडा, सूखा और पाला-रहित मौसम</strong> पसंद है। बहुत जल्दी (गर्मी में) बोने पर पौधे जल्दी
      फूल पर आ जाते हैं और पत्ती कम मिलती है; बहुत देर से बोने पर दाना भरते समय गर्मी लग जाती है।
      सभी फसलों की बुवाई का समय एक जगह देखना हो तो <a href="/articles/rabi-buvai-ka-sahi-samay">रबी बुवाई कैलेंडर</a> देखें।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- VARIETIES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🌱</span>
      <h2>मेथी की उन्नत किस्में</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>किस्म</th><th>कहाँ से</th><th>ख़ासियत</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>पूसा अर्ली बंचिंग</strong></td><td>IARI, नई दिल्ली</td><td>जल्दी पत्ती; मृदुरोमिल आसिता (डाउनी मिल्ड्यू) व गलन रोगों के प्रति प्रतिरोधी</td></tr>
        <tr><td><strong>हिसार सोनाली</strong></td><td>HAU, हिसार</td><td>जड़ गलन और माहू के प्रति कुछ हद तक सहनशील; राष्ट्रीय परीक्षणों में तुलना की किस्म</td></tr>
        <tr><td><strong>RMt-1</strong></td><td>RAU, जोबनेर (राजस्थान)</td><td>नागौर की स्थानीय मेथी से चुनी; जड़ गलन के प्रति मध्यम प्रतिरोधी, छाछ्या सहनशील</td></tr>
        <tr><td><strong>RMt-143</strong></td><td>RAU, जोबनेर</td><td>दाना लगभग 140–150 दिन में; छाछ्या के प्रति मध्यम प्रतिरोधी</td></tr>
        <tr><td><strong>RMt-305</strong></td><td>RAU, जोबनेर</td><td>अगेती — लगभग 120–125 दिन; मोटा पीला दाना; छाछ्या और जड़-गाँठ सूत्रकृमि के प्रति प्रतिरोधी</td></tr>
        <tr><td><strong>AFg-3, AFg-4</strong></td><td>ICAR-NRCSS, अजमेर</td><td>2016 में पूरे देश के लिए अधिसूचित; छाछ्या और जड़ गलन के प्रति मध्यम प्रतिरोधी</td></tr>
        <tr><td><strong>राजेंद्र क्रांति</strong></td><td>बिहार</td><td>पत्ती धब्बा रोग सहनशील; अंतरफसल के लिए उपयुक्त</td></tr>
        <tr><td><strong>लाम सिलेक्शन-1</strong></td><td>ANGRAU, आंध्र प्रदेश</td><td>छाछ्या, जड़ गलन, इल्ली और माहू के प्रति सहनशील</td></tr>
        <tr><td><strong>Co-1, Co-2</strong></td><td>TNAU, तमिलनाडु</td><td>दक्षिण भारत के लिए; Co-1 पत्ती और दाना दोनों के लिए</td></tr>
        <tr><td><strong>पूसा कसूरी</strong></td><td>IARI, नई दिल्ली</td><td>कसूरी मेथी — सुगंधित पत्ती की कई कटाई</td></tr>
      </tbody>
    </table>
    <div class="tip-box tip">
      <span class="tip-icon">🎯</span>
      <div class="tip-content">
        <strong>किस्म कैसे चुनें:</strong> सिर्फ़ हरी पत्ती बेचनी है तो पूसा अर्ली बंचिंग जैसी जल्दी पत्ती वाली
        किस्म; दाना बेचना है तो अपने राज्य में सिफ़ारिश की गई RMt या AFg किस्म; सूखी पत्ती बेचनी है तो कसूरी।
        बीज सरकारी बीज भंडार, KVK या पक्के बिल वाली दुकान से लें।
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

  <!-- FIELD PREP + SOWING -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚜</span>
      <h2>खेत की तैयारी और बुवाई का तरीका</h2>
    </div>
    <ul>
      <li><strong>मिट्टी:</strong> अच्छे पानी-निकास वाली दोमट या बलुई दोमट सबसे अच्छी। जिस खेत में पानी रुकता है, वहाँ मेथी में जड़ गलन लगभग तय है।</li>
      <li><strong>जुताई:</strong> 2–3 जुताई करके मिट्टी भुरभुरी करें। आख़िरी जुताई से पहले अच्छी सड़ी गोबर की खाद मिलाएँ।</li>
      <li><strong>क्यारियाँ:</strong> छोटी क्यारियाँ और नालियाँ बनाएँ, ताकि सिंचाई का पानी एक जगह न भरे।</li>
      <li><strong>बीज उपचार:</strong> बुवाई से पहले बीज को राइज़ोबियम कल्चर और ट्राइकोडर्मा जैसे जैविक उपचार से उपचारित करें — इससे जड़ गलन कम होती है और गाँठें अच्छी बनती हैं। तरीका और मात्रा पैकेट पर लिखी होती है।</li>
      <li><strong>कतार में बुवाई:</strong> कतार से कतार लगभग 20 सेमी और पौधे से पौधे लगभग 10–15 सेमी। कतार में बोने से निराई आसान होती है और हवा चलने से रोग कम लगते हैं।</li>
      <li><strong>बीज कितना:</strong> TNAU की सलाह में कतार की बुवाई के लिए एक हेक्टेयर (लगभग ढाई एकड़) में लगभग 12 किलो बीज बताया गया है। हरी पत्ती के लिए छिटकवाँ बोने वाले किसान आम तौर पर ज़्यादा बीज डालते हैं — अपने इलाके की सिफ़ारिश KVK से पूछें।</li>
      <li><strong>गहराई:</strong> बीज बहुत गहरा न डालें — लगभग 2–3 सेमी काफ़ी है।</li>
    </ul>
    <p><strong>कितनी खाद डालनी है, यह अपने खेत के मृदा स्वास्थ्य कार्ड (Soil Health Card) की सिफ़ारिश से तय करें, या अपने KVK / कृषि विभाग से पूछें।</strong> मेथी दलहनी है, इसलिए फॉस्फोरस वाली खाद (जैसे <a href="/articles/ssp-khad-guide">SSP</a>) इसके लिए नाइट्रोजन से ज़्यादा काम की है।</p>
  </section>

  <hr class="section-divider" />

  <!-- IRRIGATION + WEEDS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💧</span>
      <h2>सिंचाई और निराई</h2>
    </div>
    <ul>
      <li><strong>पहली सिंचाई:</strong> बुवाई के तुरंत बाद हल्की सिंचाई, ताकि जमाव एक साथ हो।</li>
      <li><strong>बाद की सिंचाई:</strong> मिट्टी देखकर — ऊपर की मिट्टी सूखने लगे तब। सर्दी में अंतर अपने आप बढ़ जाता है। <strong>हल्की सिंचाई करें, पानी भरने न दें।</strong></li>
      <li><strong>फूल और दाना भरते समय:</strong> इन दो समय पर नमी की कमी न हो — दाना पतला रह जाता है।</li>
      <li><strong>पाले की रात:</strong> पाला पड़ने की आशंका हो तो शाम को हल्की सिंचाई से फसल बचती है। पूरा तरीका <a href="/articles/pala-tushar-se-fasal-bachav">पाले से फसल बचाव</a> में है।</li>
      <li><strong>निराई:</strong> शुरू के 30–35 दिन खेत साफ़ रखें — इसी समय खरपतवार मेथी को सबसे ज़्यादा दबाते हैं। पहली निराई के साथ घने पौधे उखाड़कर पतले करें; उखाड़े पौधे हरी पत्ती में बिक जाते हैं।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- HARVEST -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✂️</span>
      <h2>कटाई — पत्ती कब, दाना कब</h2>
    </div>
    <ul>
      <li><strong>हरी पत्ती:</strong> पहली कटाई बुवाई के लगभग 20–25 दिन बाद। ज़मीन से थोड़ा ऊपर काटें, ताकि पौधा फिर से फूटे। कसूरी मेथी में कई कटाइयाँ मिलती हैं।</li>
      <li><strong>दाने वाली फसल:</strong> अगर दाना लेना है तो पत्ती की कटाई एक से ज़्यादा न करें, या बिल्कुल न करें। दाना किस्म के अनुसार लगभग 90 से 150 दिन में पकता है।</li>
      <li><strong>दाना पकने की पहचान:</strong> पत्तियाँ झड़ने लगें और फलियाँ पीली-भूरी हो जाएँ। ज़्यादा देर करने पर फलियाँ खेत में चटक जाती हैं।</li>
      <li><strong>सुखाना और गहाई:</strong> पौधे काटकर गट्ठर में धूप में सुखाएँ, फिर डंडे से पीटकर या थ्रेशर से दाना निकालें। भंडारण से पहले दाना अच्छी तरह सुखा लें।</li>
      <li><strong>कसूरी (सूखी) पत्ती:</strong> पत्तियों को छाँव में सुखाएँ — तेज़ धूप में हरा रंग और सुगंध दोनों उड़ जाते हैं।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- DISEASES: FREE FIRST -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🍂</span>
      <h2>मेथी के मुख्य रोग-कीट और पहचान</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>समस्या</th><th>पहचान</th><th>कब ज़्यादा</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>छाछ्या / चूर्णिल आसिता</strong> (पाउडरी मिल्ड्यू)</td><td>पत्तियों पर सफ़ेद पाउडर जैसी परत, बाद में पत्ती पीली होकर झड़ती है</td><td>दिन गर्म-रातें ठंडी, फरवरी के आसपास</td></tr>
        <tr><td><strong>जड़ गलन</strong></td><td>पौधे मुरझाकर सूखते हैं, जड़ भूरी-काली और सड़ी</td><td>पानी भरे खेत में, किसी भी समय</td></tr>
        <tr><td><strong>मृदुरोमिल आसिता</strong> (डाउनी मिल्ड्यू)</td><td>पत्ती ऊपर पीले धब्बे, नीचे की तरफ़ रोएँदार परत</td><td>नमी और कोहरे वाले दिन</td></tr>
        <tr><td><strong>माहू (एफिड)</strong></td><td>कोमल पत्तियों और फूलों पर छोटे हरे-काले कीट, चिपचिपी पत्ती</td><td>जनवरी-फरवरी</td></tr>
      </tbody>
    </table>
    <p><strong>पहले बिना पैसे के उपाय:</strong></p>
    <ul>
      <li><strong>प्रतिरोधी किस्म:</strong> RMt-305, AFg-3, AFg-4 जैसी छाछ्या-सहनशील किस्में सबसे सस्ता बचाव हैं।</li>
      <li><strong>फसल चक्र:</strong> एक ही खेत में हर साल मेथी न बोएँ — जड़ गलन की फफूँद मिट्टी में बनी रहती है।</li>
      <li><strong>पानी-निकास:</strong> क्यारी में पानी कभी न रुके।</li>
      <li><strong>कतार और सही दूरी:</strong> हवा चलती रहे तो छाछ्या और डाउनी दोनों कम होते हैं।</li>
      <li><strong>रोगी पौधे निकालें:</strong> जड़ गलन वाले पौधे जड़ समेत उखाड़कर खेत से बाहर नष्ट करें।</li>
      <li><strong>माहू के लिए:</strong> पीले चिपचिपे ट्रैप लगाएँ और शुरुआत में नीम आधारित घोल का छिड़काव करें। खेत की मेड़ पर लेडीबर्ड भृंग (गुबरैला) दिखे तो वह माहू खाता है — उसे बचाएँ।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CHEMICAL: PRODUCT + TIMING ONLY -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧪</span>
      <h2>ज़रूरत पड़े तो कौन सी दवा और कब</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>समस्या</th><th>दवा (तकनीकी नाम)</th><th>कब उपयुक्त</th></tr>
      </thead>
      <tbody>
        <tr><td>छाछ्या (पाउडरी मिल्ड्यू)</td><td>घुलनशील गंधक (वेटेबल सल्फर)</td><td>सफ़ेद पाउडर पहली बार दिखते ही</td></tr>
        <tr><td>जड़ गलन</td><td>बीज उपचार: ट्राइकोडर्मा; ज़्यादा फैलाव पर कार्बेन्डाजिम या कॉपर ऑक्सीक्लोराइड</td><td>बुवाई से पहले बीज पर; रोग दिखने पर जड़ के पास</td></tr>
        <tr><td>माहू</td><td>मेथी / पत्ती वाली सब्ज़ी के लिए लेबल पर दर्ज कीटनाशक — KVK से पूछें</td><td>नीम घोल से न रुके, तब</td></tr>
      </tbody>
    </table>
    <p><strong>मात्रा और छिड़काव का तरीका दवा के पैक पर छपे लेबल से लें, या अपने KVK / कृषि विभाग से पूछें।</strong></p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        <strong>हरी पत्ती पर दवा सबसे ज़्यादा सावधानी माँगती है।</strong> मेथी की पत्ती कटकर सीधे रसोई में जाती है।
        किसी भी दवा के पैक पर लिखी <strong>प्रतीक्षा अवधि</strong> (छिड़काव से कटाई तक के दिन) पूरी होने से पहले
        पत्ती न काटें, न बेचें। वही दवा इस्तेमाल करें जिसके लेबल पर यह फसल दर्ज हो, और राज्य की सिफ़ारिश अपने
        KVK या कृषि विभाग से पक्की करें — दवाओं का पंजीकरण (CIB&amp;RC) समय के साथ बदलता है।
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
      <li><strong>भारी सिंचाई या पानी भरा खेत</strong> — मेथी के नुकसान का सबसे बड़ा कारण जड़ गलन यहीं से आती है।</li>
      <li><strong>ज़्यादा यूरिया</strong> — पत्ती रसीली दिखती है, पर छाछ्या और माहू दोनों बढ़ते हैं। मेथी दलहन है, अपनी नाइट्रोजन ख़ुद बनाती है।</li>
      <li><strong>बहुत घनी बुवाई</strong> — पौधे पतले-लंबे होते हैं और बीच में हवा न चलने से रोग फैलते हैं।</li>
      <li><strong>दाने वाली फसल से बार-बार पत्ती तोड़ना</strong> — पौधा कमज़ोर होता है और दाना घटता है।</li>
      <li><strong>छिड़काव के तुरंत बाद पत्ती बेचना</strong> — लेबल की प्रतीक्षा अवधि पूरी करें; यह खाने वाले की सेहत का सवाल है।</li>
      <li><strong>दाना देर से काटना</strong> — फलियाँ चटककर दाना खेत में गिर जाता है।</li>
      <li><strong>कसूरी पत्ती को तेज़ धूप में सुखाना</strong> — रंग काला पड़ता है और सुगंध चली जाती है, दाम गिरता है।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CALENDAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>मेथी का कैलेंडर — कब क्या करें (उत्तर भारत)</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>समय</th><th>ज़रूरी काम</th></tr></thead>
      <tbody>
        <tr><td>सितंबर अंत – अक्टूबर</td><td>खेत की तैयारी, बीज ख़रीद, पत्ती वाली अगेती बुवाई</td></tr>
        <tr><td>अक्टूबर अंत – नवंबर मध्य</td><td>दाने वाली मुख्य बुवाई, बीज उपचार के साथ कतार में</td></tr>
        <tr><td>बुवाई के 20–25 दिन</td><td>पहली निराई, पौधे पतले करना, पहली हरी पत्ती बिक्री</td></tr>
        <tr><td>दिसंबर – जनवरी</td><td>पाले से बचाव की सिंचाई, माहू की निगरानी, पीले ट्रैप</td></tr>
        <tr><td>जनवरी – फरवरी</td><td>फूल और फली — नमी बनाए रखें, छाछ्या पर नज़र</td></tr>
        <tr><td>फरवरी अंत – मार्च</td><td>फलियाँ पीली होते ही कटाई, सुखाना, गहाई</td></tr>
        <tr><td>मार्च – अप्रैल</td><td>दाना सुखाकर भंडारण या मंडी में बिक्री</td></tr>
      </tbody>
    </table>
  </section>

  <hr class="section-divider" />

  <!-- SELLING -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💰</span>
      <h2>मेथी कहाँ और कैसे बेचें</h2>
    </div>
    <ul>
      <li><strong>हरी पत्ती:</strong> सुबह जल्दी काटकर छोटे गट्ठर बनाएँ और उसी दिन नज़दीकी सब्ज़ी मंडी पहुँचाएँ — मेथी की पत्ती एक दिन में मुरझा जाती है। आज का भाव <a href="/bhav/methi-leaves">मेथी पत्ती का मंडी भाव</a> पर देखें।</li>
      <li><strong>दाना:</strong> राजस्थान, मध्य प्रदेश और गुजरात की मसाला मंडियों में मेथी दाने की बड़ी ख़रीद होती है। साफ़, एक रंग का, सूखा दाना अच्छा भाव पाता है। भाव <a href="/bhav/methi-seeds">मेथी दाने का मंडी भाव</a> पर देखें।</li>
      <li><strong>कसूरी (सूखी) पत्ती:</strong> साफ़ पैकिंग में सीधे दुकानों या मसाला व्यापारियों को। अपना माल <a href="/krashi_bajar">कृषि बाज़ार</a> पर भी डाल सकते हैं।</li>
    </ul>
    <p>मंडी भाव जानकारी के लिए हैं और रोज़ बदलते हैं — बेचने से पहले उसी दिन मंडी से भाव पक्का करें।</p>
  </section>

  <hr class="section-divider" />

  <!-- CONCLUSION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✅</span>
      <h2>निष्कर्ष</h2>
    </div>
    <p>
      तीन बातें याद रखें। पहली — <strong>अक्टूबर अंत से नवंबर मध्य की बुवाई</strong> दाने वाली मेथी के लिए सबसे
      सुरक्षित है। दूसरी — <strong>पानी भरने न दें</strong>; जड़ गलन यहीं से आती है। तीसरी —
      <strong>छाछ्या-सहनशील किस्म और कतार की बुवाई</strong> किसी भी दवा से सस्ता बचाव है।
    </p>
    <p><strong>मेथी में कमाई पानी के सही हिसाब से है — कम पानी, ज़्यादा सेहत।</strong></p>
  </section>
"""

FAQS = [
    ("मेथी की बुवाई कब करें?",
     "उत्तर और मध्य भारत के मैदानों में मेथी <strong>अक्टूबर से नवंबर</strong> में बोई जाती है; दाने वाली फसल के लिए अक्टूबर के आख़िर से नवंबर का पहला पखवाड़ा सबसे सुरक्षित है। सिर्फ़ हरी पत्ती के लिए सितंबर के आख़िर से बुवाई शुरू हो सकती है।"),
    ("मेथी कितने दिन में तैयार होती है?",
     "मेथी की हरी पत्ती <strong>लगभग 20–25 दिन</strong> में पहली कटाई लायक हो जाती है। दाना किस्म के अनुसार लगभग 90 से 150 दिन में पकता है, और कसूरी मेथी का दाना लगभग 150–160 दिन लेता है।"),
    ("मेथी की सबसे अच्छी किस्म कौन सी है?",
     "हरी पत्ती के लिए <strong>पूसा अर्ली बंचिंग</strong>, और दाने के लिए RMt-305, AFg-3 या AFg-4 जैसी छाछ्या-सहनशील किस्में अच्छी मानी जाती हैं। सुगंधित सूखी पत्ती के लिए कसूरी मेथी (पूसा कसूरी) बोई जाती है। अपने राज्य की सिफ़ारिश KVK से पक्की करें।"),
    ("मेथी में सफ़ेद पाउडर (छाछ्या) क्यों आता है?",
     "पत्तियों पर सफ़ेद पाउडर <strong>चूर्णिल आसिता (पाउडरी मिल्ड्यू)</strong> नाम का फफूँद रोग है, जो गर्म दिन और ठंडी रातों में फैलता है। सहनशील किस्म, कतार की बुवाई और सही दूरी से यह कम होता है; ज़रूरत पड़ने पर घुलनशील गंधक का छिड़काव लेबल के अनुसार किया जाता है।"),
    ("मेथी के पौधे सूख क्यों जाते हैं?",
     "मेथी के पौधे मुरझाकर सूखना ज़्यादातर <strong>जड़ गलन</strong> है, जो खेत में पानी भरने से आती है। हल्की सिंचाई, अच्छा पानी-निकास, फसल चक्र और ट्राइकोडर्मा से बीज उपचार इसका मुख्य बचाव है।"),
    ("एक हेक्टेयर में मेथी का कितना बीज लगता है?",
     "TNAU की सलाह में कतार की बुवाई के लिए <strong>एक हेक्टेयर (लगभग ढाई एकड़) में लगभग 12 किलो बीज</strong> बताया गया है। हरी पत्ती के लिए छिटकवाँ बुवाई में किसान ज़्यादा बीज डालते हैं — अपने इलाके की सिफ़ारिश KVK से लें।"),
    ("देसी मेथी और कसूरी मेथी में क्या अंतर है?",
     "देसी मेथी <strong>तेज़ बढ़ती है और पत्ती व दाना दोनों</strong> देती है, जबकि कसूरी मेथी धीमी बढ़ती है, उसकी पत्ती छोटी और ज़्यादा सुगंधित होती है और कई बार काटी जाती है। कसूरी मेथी ज़्यादातर सुखाई हुई पत्ती के रूप में बिकती है।"),
    ("मेथी को पाले से कैसे बचाएँ?",
     "पाले की आशंका वाली रात <strong>शाम को हल्की सिंचाई</strong> करें — नम मिट्टी पौधों के पास का तापमान थोड़ा ऊपर रखती है। फूल के समय पाला सबसे ज़्यादा नुकसान करता है; कसूरी मेथी पाला काफ़ी सह लेती है।"),
]

ARTICLE = {
    "slug": "methi-ki-kheti",
    "date": "2026-10-21",
    "date_label": "अक्टूबर 2026",
    "read_time": 10,
    "word_count": 2400,
    "lang": "hi",

    "section": "सब्ज़ी की खेती",
    "cat_label": "सब्ज़ी की खेती",
    "cat_query": "sabji",
    "breadcrumb_leaf": "मेथी की खेती",

    "title": "मेथी की खेती कैसे करें? बुवाई अक्टूबर-नवंबर, 20–25 दिन में पत्ती",
    "description": "मेथी की बुवाई अक्टूबर से नवंबर, हरी पत्ती 20–25 दिन में और दाना 90–150 दिन में। पूसा अर्ली बंचिंग, RMt-305, AFg किस्में, कसूरी मेथी, छाछ्या और जड़ गलन से बचाव।",
    "keywords": "मेथी की खेती, methi ki kheti, मेथी की बुवाई कब करें, methi ki buvai kab kare, कसूरी मेथी की खेती, kasuri methi, मेथी की उन्नत किस्में, RMt 305, पूसा अर्ली बंचिंग, fenugreek farming India, methi me safed rog, मेथी में छाछ्या",

    "og_title": "मेथी की खेती — बुवाई, किस्में, कटाई और रोग से बचाव | KrashiMitra.in",
    "og_desc": "अक्टूबर-नवंबर में बोई मेथी 20–25 दिन में पत्ती देती है। जड़ गलन और सफ़ेद पाउडर से फसल कैसे बचाएँ।",

    "hero_image": ("images/articles/methi-ki-kheti.webp",
                   "ताज़ा काटी गई हरी मेथी के गट्ठर",
                   "ताज़ा काटी गई हरी मेथी के गट्ठर — बुवाई के लगभग 20–25 दिन बाद पहली पत्ती इसी तरह मंडी जाती है।"),

    "headline": "मेथी की खेती — बुवाई का समय, उन्नत किस्में, कटाई और रोग से बचाव",
    "headline_en": "Fenugreek (Methi) Farming in India — Sowing Time, Varieties, Harvest and Disease Control",
    "schema_desc": "मेथी की खेती की पूरी जानकारी: देसी और कसूरी मेथी, बुवाई का समय, पूसा अर्ली बंचिंग, RMt-305 व AFg जैसी किस्में, बीज उपचार, सिंचाई, पत्ती और दाने की कटाई, छाछ्या व जड़ गलन से बचाव, और बिक्री।",
    "schema_keywords": ["मेथी की खेती", "कसूरी मेथी", "मेथी की किस्में", "fenugreek farming", "methi ki kheti"],

    "h1": "मेथी की खेती — बुवाई से बिक्री तक",
    "h1_en": "Fenugreek (Methi) Farming — From Sowing to Selling",
    "share_title": "मेथी की खेती — अक्टूबर-नवंबर में बुवाई, 20–25 दिन में पहली पत्ती",
    "hero_excerpt": "मेथी पहले हरी पत्ती में और फिर दाने में — दो बार कमाई देती है। पर पानी भरा खेत और सफ़ेद पाउडर वाला रोग पूरी फसल बिगाड़ सकते हैं।",
    "lede_h2": "मेथी की खेती — एक नज़र में",

    "badges": [("badge-season", "🗓️ अक्टूबर – नवंबर"),
               ("badge-location", "📍 उत्तर व मध्य भारत"),
               ("badge-disease", "🌿 पत्ती 20–25 दिन")],

    "quick_facts": [("", "🗓️", "अक्टू–नवं", "बुवाई का समय"),
                    ("warn", "✂️", "20–25 दिन", "पहली हरी पत्ती"),
                    ("danger", "💧", "पानी न भरे", "जड़ गलन से बचाव")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("methi-leaves", "मेथी पत्ती का भाव"), ("methi-seeds", "मेथी दाने का भाव"),
                   ("coriander-leaves", "हरे धनिये का भाव")],

    "card": {
        "emoji": "🌿",
        "bg": "#ecfdf5",
        "accent": "#059669",
        "tag": "मेथी · खेती",
        "tag_bg": "#d1fae5",
        "tag_color": "#047857",
        "title": "मेथी की खेती — अक्टूबर-नवंबर बुवाई, 20–25 दिन में पत्ती",
        "cats": "sabji",
        "keywords": "मेथी methi fenugreek कसूरी kasuri खेती बुवाई किस्म RMt पूसा छाछ्या जड़ गलन पत्ती दाना",
    },

    "related": [
        (f"{SITE}/articles/rabi-buvai-ka-sahi-samay", "#15803d", "🗓️", "रबी · बुवाई",
         "रबी फसलों की बुवाई का सही समय — पूरा कैलेंडर"),
        (f"{SITE}/articles/dhaniya-ki-kheti-mp", "#16a34a", "🌱", "धनिया · खेती",
         "धनिया की खेती — बुवाई से बिक्री तक"),
        (f"{SITE}/articles/gajar-ki-kheti", "#ea580c", "🥕", "गाजर · खेती",
         "गाजर की खेती — अक्टूबर में बुवाई"),
        (f"{SITE}/articles/pala-tushar-se-fasal-bachav", "#0369a1", "❄️", "पाला · बचाव",
         "पाले से फसल कैसे बचाएँ"),
        (f"{SITE}/bhav/methi-leaves", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "मेथी का आज का मंडी भाव — राज्यवार LIVE रेट"),
        (f"{SITE}/chat", "#2e7d32", "🤖", "AI · सहायता",
         "फसल की फोटो भेजें — AI से तुरंत पहचान"),
    ],
}
