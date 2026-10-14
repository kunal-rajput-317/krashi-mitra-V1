# -*- coding: utf-8 -*-
# धान का कंडुआ रोग (false smut) — October 2026. Paddy is the site's biggest
# demand this season ("dhan is very demanding", owner, Oct 2026) and the
# kandua balls are visible in fields right now, when farmers search for them.
#
# Sources:
#   - Pathogen Ustilaginoidea virens (syn. Villosiclava virens); infection at
#     booting, symptoms 2–3 weeks after flowering; balls white → orange-yellow
#     → olive-green/black; favoured by rain/drizzle and >90% humidity at
#     booting–flowering, 25–35 °C, heavy nitrogen; hybrids more susceptible.
#     (ICAR epubs: IJAgS, Indian Farming, IPPJ, IJPP; Vikaspedia.)
#   - Yield loss 0.82–17.09% across 24 varieties (IPPJ, "Evaluation of yield
#     losses and management practices of false smut in rice").
#   - Fungicides with trial evidence at booting: propiconazole, copper
#     hydroxide, azoxystrobin + difenoconazole (IIRR multi-location trials).
#     Named with timing only — no dose (LEGAL_RULES §2); none is on the banned
#     list in tests/test_legal_guardrails.py.
#   - Ustiloxins: mycotoxins identified in false-smut balls.
#   - FCI paddy spec: damaged, discoloured, sprouted and weevilled grains up to
#     5% (same figure as dhan-nami-mandi-rejection).

SITE = "https://krashimitra.in"

BODY = r"""
  <!-- INTRODUCTION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📖</span>
      <h2>भूमिका</h2>
    </div>
    <p>
      धान की बालियाँ भर रही हैं, और कुछ बालियों में दाने की जगह एक <strong>पीली-नारंगी मखमली गेंद</strong>
      दिख रही है, जो छूने पर हाथ में पीला या हरा-काला पाउडर छोड़ देती है। यह <strong>कंडुआ रोग</strong>
      (अंग्रेज़ी में false smut) है। कई जगह इसे <strong>हल्दी रोग</strong> या <strong>हरदिया</strong> भी कहते
      हैं।
    </p>
    <p>
      कई गाँवों में एक पुरानी मान्यता है कि कंडुआ "लक्ष्मी" है — जिस साल यह दिखे, उस साल फसल अच्छी होगी।
      इसमें आधा सच है: कंडुआ अक्सर उन्हीं खेतों में आता है जहाँ फसल घनी, हरी-भरी और खाद से भरपूर होती है।
      पर बाक़ी आधा सच यह है कि <strong>हर गेंद एक दाना कम है</strong>, गेंदों का पाउडर अगले साल के लिए खेत
      में बीज छोड़ जाता है, और बदरंग दानों वाला धान मंडी में कमज़ोर पड़ता है।
    </p>
    <p>
      इस लेख की सबसे ज़रूरी बात पहले ही कह देते हैं: <strong>गेंद दिखने के बाद कोई दवा उसे ठीक नहीं
      करती।</strong> इस साल आप नुकसान को फैलने से रोक सकते हैं और बीज बचा सकते हैं; असली बचाव अगले साल
      बूटिंग (गाभा) अवस्था में होता है। दोनों बातें नीचे हैं।
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

  <!-- WHAT IS IT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔍</span>
      <h2>कंडुआ रोग क्या है?</h2>
    </div>
    <p>
      कंडुआ एक <strong>फफूंद रोग</strong> है, जिसकी फफूंद का नाम <em>अस्टिलेजिनोइडिया वाइरेंस</em>
      (Ustilaginoidea virens) है। यह फफूंद धान के फूल में घुसकर दाने की जगह ले लेती है, और दाने की जगह
      बीजाणुओं (स्पोर) से भरी एक गेंद बन जाती है।
    </p>
    <p>
      संक्रमण <strong>बूटिंग (गाभा) से फूल आने के समय</strong> होता है, पर गेंदें फूल आने के लगभग
      <strong>दो-तीन हफ़्ते बाद</strong> दिखती हैं। यानी जब किसान को रोग दिखता है, तब तक संक्रमण हो चुका
      होता है — इसीलिए दिखने के बाद छिड़काव का फ़ायदा नहीं।
    </p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        आम तौर पर एक बाली में कुछ ही दाने गेंद बनते हैं, बाक़ी दाने सामान्य रहते हैं। इसलिए कंडुआ से पूरी फसल
        नहीं जाती — पर जिस साल बूटिंग के समय लगातार बारिश और नमी रही, उस साल नुकसान काफ़ी बढ़ जाता है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- IDENTIFICATION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">👁️</span>
      <h2>पहचान — गेंद का रंग बताता है उम्र</h2>
    </div>
    <ol>
      <li><strong>शुरुआत:</strong> दाने के छिलके के बीच से एक छोटी सफ़ेद-सी परत बाहर झाँकती है।</li>
      <li><strong>कुछ दिन बाद:</strong> वह फूलकर दाने से बड़ी, <strong>पीली-नारंगी मखमली गेंद</strong> बन जाती है।</li>
      <li><strong>पकने पर:</strong> गेंद का रंग <strong>हरा-जैतूनी और फिर काला</strong> होता जाता है, और ऊपर की परत फटकर पाउडर उड़ने लगता है।</li>
      <li><strong>हाथ लगाने पर:</strong> उँगलियों पर पीला, हरा या काला पाउडर लग जाता है — यही बीजाणु हैं।</li>
    </ol>
    <table class="article-table">
      <thead>
        <tr><th>पहचान बिंदु</th><th>✅ स्वस्थ बाली</th><th>❌ कंडुआ वाली बाली</th></tr>
      </thead>
      <tbody>
        <tr><td>दाना</td><td class="healthy">छिलके में बंद, लंबा, सुनहरा होता हुआ</td><td class="diseased">कुछ दानों की जगह गोल मखमली गेंद</td></tr>
        <tr><td>रंग</td><td class="healthy">हरा से सुनहरा</td><td class="diseased">पीला-नारंगी, फिर हरा-काला</td></tr>
        <tr><td>छूने पर</td><td class="healthy">कुछ नहीं लगता</td><td class="diseased">हाथ पर पाउडर लग जाता है</td></tr>
        <tr><td>आकार</td><td class="healthy">दाने जितना</td><td class="diseased">दाने से बड़ी, बाहर निकली गेंद</td></tr>
        <tr><td>खेत में</td><td class="healthy">—</td><td class="diseased">अक्सर घनी, ज़्यादा हरी और ज़्यादा खाद वाली जगहों पर</td></tr>
      </tbody>
    </table>
    <div class="tip-box tip">
      <span class="tip-icon">🔎</span>
      <div class="tip-content">
        कंडुआ को <a href="/articles/dhan-jhonka-rog">गर्दन झोंका (ब्लास्ट)</a> से अलग पहचानिए: झोंके में बाली की
        <strong>गर्दन</strong> काली-भूरी होकर टूट जाती है और पूरी बाली सफ़ेद-खाली रह जाती है; कंडुआ में गर्दन
        ठीक रहती है और <strong>अलग-अलग दानों</strong> की जगह गेंदें बनती हैं।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- WHY THIS YEAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🌧️</span>
      <h2>कंडुआ किस खेत में और किस साल ज़्यादा आता है?</h2>
    </div>
    <ul>
      <li><strong>बूटिंग से फूल आने तक बारिश या बूँदाबाँदी:</strong> सबसे बड़ा कारण। बहुत ज़्यादा नमी (90% से ऊपर) और 25–35 डिग्री के आसपास तापमान इस फफूंद को सबसे ज़्यादा पसंद है।</li>
      <li><strong>ज़्यादा नाइट्रोजन (यूरिया):</strong> बहुत हरी, घनी फसल में कंडुआ ज़्यादा दिखता है। यही वजह है कि लोग इसे "अच्छी फसल की निशानी" मान लेते हैं।</li>
      <li><strong>हाइब्रिड और लंबी अवधि की किस्में:</strong> शोध में हाइब्रिड धान इसके प्रति ज़्यादा संवेदनशील पाए गए हैं।</li>
      <li><strong>पिछले साल का रोगी खेत और रोगी बीज:</strong> गेंदों से गिरे बीजाणु और कठोर गाँठें (स्क्लेरोशिया) मिट्टी में बचे रहते हैं, और रोगी खेत का बीज रोग साथ लाता है।</li>
      <li><strong>मेड़ों पर घास:</strong> कुछ घासें इस फफूंद को आश्रय देती हैं।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- LOSS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📉</span>
      <h2>नुकसान कितना होता है?</h2>
    </div>
    <p>
      एक शोध में 24 किस्मों पर कंडुआ का असर मापा गया: संक्रमण लगभग <strong>5% से 49%</strong> बालियों तक
      और उपज का नुकसान लगभग <strong>1% से 17%</strong> तक पाया गया। नुकसान तीन तरह से होता है:
    </p>
    <table class="article-table">
      <thead><tr><th>नुकसान</th><th>कैसे</th></tr></thead>
      <tbody>
        <tr><td>उपज</td><td>गेंद बना हर दाना खाली; गंभीर हालत में आसपास के दाने भी हल्के रह जाते हैं</td></tr>
        <tr><td>गुणवत्ता</td><td>पाउडर लगने से दाने बदरंग होते हैं। सरकारी ख़रीद में क्षतिग्रस्त, बदरंग, अंकुरित और घुन लगे दाने मिलाकर <strong>5%</strong> तक ही चलते हैं</td></tr>
        <tr><td>अगला साल</td><td>गेंदों के बीजाणु और गाँठें खेत में रह जाती हैं; रोगी धान को बीज बनाने पर रोग अगली फसल में जाता है</td></tr>
        <tr><td>पशु</td><td>गेंदों में <strong>उस्टिलॉक्सिन</strong> नाम के विषैले तत्व पाए गए हैं; इसलिए गेंदों से भरा भूसा या दाना पशुओं को खिलाने से बचें</td></tr>
      </tbody>
    </table>
  </section>

  <hr class="section-divider" />

  <!-- ── AD SLOT 2 ── -->
  <div class="ad-slot responsive" aria-label="विज्ञापन">
    <div class="ad-slot-label">विज्ञापन</div>
    <div class="ad-slot-inner">
      <div class="km-ad-slot" data-slot="4489195916" data-format="auto"></div>
    </div>
  </div>

  <!-- RIGHT NOW -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧺</span>
      <h2>इस साल गेंदें दिख चुकी हैं — अब क्या करें?</h2>
    </div>
    <p>
      दवा छिड़कने के पैसे बचाइए — इस अवस्था में उससे गेंद ठीक नहीं होगी। ये बिना पैसे वाले काम करिए:
    </p>
    <ol>
      <li><strong>रोगी बालियाँ थैली में तोड़ें:</strong> सुबह ओस रहते, जब पाउडर कम उड़ता है, गेंद वाली बालियों पर पॉलिथीन की थैली चढ़ाकर उन्हें तोड़ लें। खुले हाथ से झाड़ने पर पाउडर पूरे खेत में फैलता है।</li>
      <li><strong>तोड़ी बालियाँ खेत से दूर गाड़ दें:</strong> इन्हें मेड़ पर न फेंकें।</li>
      <li><strong>रोगी हिस्से की कटाई अलग:</strong> जिस हिस्से में गेंदें ज़्यादा हैं, उसकी कटाई और मड़ाई बाक़ी खेत से अलग करें।</li>
      <li><strong>इस खेत से बीज न रखें:</strong> अगले साल का बीज किसी साफ़ खेत से या प्रमाणित बीज लें।</li>
      <li><strong>ओसाई और सफ़ाई:</strong> मड़ाई के बाद अच्छी ओसाई करें, ताकि गेंदें और पाउडर निकल जाएँ और धान मंडी के मानक पर रहे। धान सुखाने और साफ़ करने के तरीके <a href="/articles/dhan-nami-mandi-rejection">धान की नमी और मंडी रिजेक्शन वाले लेख</a> में हैं।</li>
      <li><strong>हाथ और कपड़े:</strong> बालियाँ तोड़ने के बाद हाथ धोएँ, और पाउडर वाले कपड़े में दूसरे खेत में न जाएँ।</li>
    </ol>
  </section>

  <hr class="section-divider" />

  <!-- NEXT YEAR: FREE MEASURES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🛡️</span>
      <h2>अगले साल के लिए — बिना पैसे की रोकथाम</h2>
    </div>
    <ul>
      <li><strong>साफ़ बीज:</strong> प्रमाणित बीज या रोगमुक्त खेत का बीज। बोने से पहले नमक के घोल में बीज डुबोकर ऊपर तैरते हल्के और रोगी दाने निकाल दें, फिर साफ़ पानी से धोकर बोएँ।</li>
      <li><strong>बीज उपचार:</strong> ट्राइकोडर्मा या स्यूडोमोनास जैसे जैविक उपचार, या KVK का सुझाया फफूंदनाशी — कौन सा और कितना, यह पैक के लेबल और KVK से लें। तरीका <a href="/articles/beej-upchar-vidhi">बीज उपचार वाले लेख</a> में।</li>
      <li><strong>संतुलित यूरिया:</strong> नाइट्रोजन एक बार में ज़्यादा न डालें, किस्तों में डालें, और बाली निकलने के बाद अतिरिक्त यूरिया से बचें। मात्रा मृदा स्वास्थ्य कार्ड से — समय की जानकारी <a href="/articles/dhan-me-urea-kab-kitna">धान में यूरिया कब डालें</a> में है।</li>
      <li><strong>किस्म का चुनाव:</strong> जिस खेत में हर साल कंडुआ आता हो, वहाँ अपने इलाके के लिए कम संवेदनशील बताई गई किस्म के बारे में KVK से पूछें।</li>
      <li><strong>गहरी जुताई:</strong> कटाई के बाद गहरी जुताई से मिट्टी में पड़ी गाँठें नीचे दब जाती हैं।</li>
      <li><strong>मेड़ों की सफ़ाई:</strong> मेड़ों और नालियों की घास साफ़ रखें।</li>
      <li><strong>खेत में लगातार पानी नहीं:</strong> जहाँ हो सके, बीच-बीच में खेत सुखाकर फिर पानी देना (AWD) नमी और रोग दोनों घटाता है।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CHEMICAL: TIMING ONLY -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧪</span>
      <h2>दवा — कौन सी और कब (सिर्फ़ बचाव के लिए)</h2>
    </div>
    <p>
      जिन खेतों में हर साल कंडुआ आता है, या बूटिंग के समय लगातार बारिश का अनुमान हो, वहाँ <strong>गेंद दिखने
      से पहले</strong> फफूंदनाशी का छिड़काव बचाव करता है। समय सबसे ज़रूरी है:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>दवा (तकनीकी नाम)</th><th>कब उपयुक्त</th></tr>
      </thead>
      <tbody>
        <tr><td>प्रोपिकोनाज़ोल (Propiconazole)</td><td>बूटिंग (गाभा) अवस्था में; ज़रूरत हो तो फूल आने के समय दोहराना — KVK की सलाह से</td></tr>
        <tr><td>कॉपर हाइड्रॉक्साइड (Copper hydroxide)</td><td>बूटिंग अवस्था में, बचाव के लिए</td></tr>
        <tr><td>एज़ॉक्सीस्ट्रोबिन + डाइफ़ेनोकोनाज़ोल (Azoxystrobin + Difenoconazole)</td><td>बूटिंग अवस्था में, बचाव के लिए</td></tr>
      </tbody>
    </table>
    <p><strong>मात्रा और छिड़काव का तरीका दवा के पैक पर छपे लेबल से लें, या अपने KVK / कृषि विभाग से पूछें।</strong></p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        पैक पर देखें कि दवा <strong>धान और इस रोग</strong> के लिए CIB&amp;RC में पंजीकृत है, और कटाई से पहले का
        प्रतीक्षा काल लेबल के अनुसार रखें। <strong>बाली में गेंद दिखने के बाद छिड़काव से रोग ठीक नहीं होता</strong>
        — उस समय दवा बेचने वाले की बात पर पैसा न लगाएँ। राज्य और ज़िले की सिफ़ारिशें अलग हो सकती हैं, इसलिए अपने
        KVK या कृषि विभाग से पुष्टि करें।
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
      <li><strong>गेंद दिखने के बाद दवा छिड़कना</strong> — पैसा जाता है, गेंद नहीं।</li>
      <li><strong>"लक्ष्मी आई है" मानकर छोड़ देना</strong> — गेंदों का पाउडर अगले साल का रोग बनता है।</li>
      <li><strong>रोगी बालियों को खुले हाथ से झाड़ना या मेड़ पर फेंकना</strong> — बीजाणु पूरे खेत में फैलते हैं।</li>
      <li><strong>रोगी खेत का धान बीज के लिए रखना</strong> — रोग अगले साल साथ जाता है।</li>
      <li><strong>बाली निकलने के बाद यूरिया डालना</strong> — दाने को फ़ायदा कम, रोग को ज़्यादा।</li>
      <li><strong>गेंदों वाला भूसा या दाना पशुओं को खिलाना</strong> — इसमें विषैले तत्व पाए गए हैं।</li>
      <li><strong>बिना ओसाई के मंडी ले जाना</strong> — बदरंग दाने और कचरा भाव और ग्रेड दोनों गिराते हैं।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CALENDAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>कंडुआ से बचाव — कब क्या करें</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>समय</th><th>ज़रूरी काम</th></tr></thead>
      <tbody>
        <tr><td>अभी (अक्टूबर, बाली भरते समय)</td><td>रोगी बालियाँ थैली में तोड़कर गाड़ें; रोगी हिस्से की कटाई अलग; इस खेत का बीज न रखें</td></tr>
        <tr><td>कटाई और मड़ाई</td><td>अच्छी ओसाई, धूप में सुखाना; गेंदों वाला भूसा पशुओं से दूर</td></tr>
        <tr><td>कटाई के बाद</td><td>गहरी जुताई; मेड़ों की घास साफ़</td></tr>
        <tr><td>अगले साल नर्सरी से पहले</td><td>प्रमाणित बीज, नमक के घोल से छँटाई, बीज उपचार (KVK की सलाह से)</td></tr>
        <tr><td>रोपाई के बाद</td><td>यूरिया किस्तों में, मृदा स्वास्थ्य कार्ड के अनुसार</td></tr>
        <tr><td>बूटिंग (गाभा) अवस्था</td><td>मौसम देखें; पिछला इतिहास हो या बारिश का अनुमान हो तो KVK की सलाह से बचाव का छिड़काव</td></tr>
        <tr><td>फूल आने के 2-3 हफ़्ते बाद</td><td>खेत में घूमकर गेंदों की निगरानी</td></tr>
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
      कंडुआ के बारे में तीन बातें याद रखिए: <strong>गेंद दिखने के बाद दवा काम नहीं करती</strong>;
      <strong>रोगी बालियाँ थैली में तोड़कर गाड़ें और इस खेत का बीज न रखें</strong>; और <strong>असली बचाव
      अगले साल — साफ़ बीज, संतुलित यूरिया और बूटिंग पर निगरानी</strong>।
    </p>
    <p>
      धान बेचने से पहले आज का भाव <a href="/bhav/paddy-common">धान के मंडी भाव</a> पर और सरकारी रेट
      <a href="/articles/dhan-msp-sarkari-rate-2026-27">धान MSP 2026-27</a> पर देख लें।
    </p>
    <p><strong>कंडुआ लक्ष्मी नहीं, चेतावनी है — अगले साल की तैयारी इसी साल की कटाई से शुरू होती है।</strong></p>
  </section>
"""

FAQS = [
    ("धान में कंडुआ रोग क्या है?",
     "कंडुआ (false smut) धान का एक <strong>फफूंद रोग</strong> है, जिसमें बाली के कुछ दानों की जगह पीली-नारंगी मखमली गेंदें बन जाती हैं, जो बाद में हरी-काली होकर पाउडर छोड़ती हैं। इसे कई जगह हल्दी रोग या हरदिया भी कहते हैं।"),
    ("धान में कंडुआ रोग की दवा क्या है?",
     "<strong>गेंद दिखने के बाद कोई दवा उसे ठीक नहीं करती</strong>। बचाव के लिए बूटिंग (गाभा) अवस्था में प्रोपिकोनाज़ोल, कॉपर हाइड्रॉक्साइड या एज़ॉक्सीस्ट्रोबिन + डाइफ़ेनोकोनाज़ोल जैसे फफूंदनाशी इस्तेमाल होते हैं; मात्रा पैक के लेबल या KVK से लें।"),
    ("कंडुआ रोग कब लगता है?",
     "कंडुआ का संक्रमण <strong>बूटिंग से फूल आने के समय</strong> होता है, और गेंदें फूल आने के लगभग दो-तीन हफ़्ते बाद दिखती हैं। उस समय बारिश, बूँदाबाँदी और बहुत ज़्यादा नमी रोग बढ़ाती है।"),
    ("कंडुआ रोग से कितना नुकसान होता है?",
     "एक शोध में 24 किस्मों पर उपज का नुकसान <strong>लगभग 1% से 17%</strong> तक मापा गया। इसके अलावा बदरंग दाने मंडी में ग्रेड गिराते हैं और रोगी खेत का बीज अगले साल रोग फैलाता है।"),
    ("क्या कंडुआ रोग अच्छी फसल की निशानी है?",
     "<strong>नहीं।</strong> कंडुआ अक्सर घनी, ज़्यादा खाद वाली फसल में दिखता है, इसलिए यह मान्यता बनी; पर हर गेंद एक खोया दाना है और उसका पाउडर अगले साल के लिए खेत में रोग छोड़ता है।"),
    ("कंडुआ वाले धान को बीज के लिए रख सकते हैं?",
     "<strong>नहीं, कंडुआ वाले खेत का धान बीज के लिए न रखें।</strong> अगले साल प्रमाणित बीज या किसी रोगमुक्त खेत का बीज लें, और बोने से पहले नमक के घोल से हल्के दाने छाँट दें।"),
    ("कंडुआ वाला भूसा पशुओं को खिला सकते हैं?",
     "कंडुआ की गेंदों में <strong>उस्टिलॉक्सिन नाम के विषैले तत्व</strong> पाए गए हैं, इसलिए गेंदों से भरा भूसा या दाना पशुओं को खिलाने से बचें। पशु में कोई लक्षण दिखे तो पंजीकृत पशु चिकित्सक को दिखाएँ।"),
    ("कंडुआ और झोंका रोग में क्या फ़र्क है?",
     "झोंका (गर्दन ब्लास्ट) में <strong>बाली की गर्दन</strong> काली होकर टूटती है और पूरी बाली खाली रह जाती है; कंडुआ में गर्दन ठीक रहती है और <strong>अलग-अलग दानों</strong> की जगह मखमली गेंदें बनती हैं।"),
]

ARTICLE = {
    "slug": "dhan-kandua-rog",
    "date": "2026-10-13",
    "date_label": "अक्टूबर 2026",
    "read_time": 9,
    "word_count": 2200,
    "lang": "hi",

    "section": "फसल रोग",
    "cat_label": "धान के रोग",
    "cat_query": "keet",
    "breadcrumb_leaf": "धान का कंडुआ रोग",

    "title": "धान में कंडुआ रोग: बाली में पीली गेंद दिखे तो क्या करें? (2026)",
    "description": "बाली में पीली-हरी मखमली गेंद = कंडुआ (false smut)। गेंद दिखने के बाद दवा से इलाज नहीं — नुकसान 1–17% तक। अभी क्या करें, बीज कैसे बचाएँ, अगले साल बचाव कब।",
    "keywords": "धान में कंडुआ रोग, dhan me kandua rog, कंडुआ रोग की दवा, kandua rog ki dawa, धान का हल्दी रोग, हरदिया रोग, false smut of rice, धान की बाली में पीली गेंद, लक्ष्मी रोग धान",

    "og_title": "धान का कंडुआ रोग — लक्ष्मी नहीं, चेतावनी | KrashiMitra.in",
    "og_desc": "बाली में पीली गेंदें दिख रही हैं? दवा का पैसा बचाइए — अभी क्या करें और अगले साल बचाव कब होता है।",

    "hero_image": ("images/articles/dhan-kandua-rog.webp",
                   "धान की हरी बाली पर कंडुआ रोग की पीली-नारंगी गेंद",
                   "धान की बाली पर कंडुआ (false smut) की पीली-नारंगी गेंद। बाक़ी दाने सामान्य हैं — कंडुआ में आम तौर पर कुछ ही दाने गेंद बनते हैं।"),

    "headline": "धान में कंडुआ रोग — पहचान, नुकसान और बचाव",
    "headline_en": "False Smut (Kandua) of Rice — Identification, Loss and Prevention",
    "schema_desc": "धान के कंडुआ रोग (false smut, Ustilaginoidea virens) की पहचान, यह किस मौसम और खेत में ज़्यादा आता है, उपज-गुणवत्ता-बीज पर असर, गेंद दिखने के बाद क्या करें, और अगले साल बूटिंग अवस्था में बचाव।",
    "schema_keywords": ["धान में कंडुआ रोग", "false smut rice", "कंडुआ रोग की दवा", "धान का हल्दी रोग", "Ustilaginoidea virens"],

    "h1": "धान का कंडुआ रोग — बाली में पीली गेंदें",
    "h1_en": "False Smut of Paddy — What to Do Now and Next Season",
    "share_title": "धान की बाली में पीली गेंदें? यह कंडुआ है — अभी क्या करें",
    "hero_excerpt": "बाली में दाने की जगह पीली-नारंगी मखमली गेंद — यह कंडुआ रोग है। गेंद दिखने के बाद दवा काम नहीं करती; अभी बीज बचाइए और अगले साल का बचाव समझिए।",
    "lede_h2": "कंडुआ रोग — एक नज़र में",

    "badges": [("badge-disease", "🍄 फफूंद रोग"),
               ("badge-season", "🗓️ सितंबर–अक्टूबर"),
               ("badge-location", "📍 UP · बिहार · पंजाब · हरियाणा")],

    "quick_facts": [("danger", "📉", "1–17%", "उपज का नुकसान (शोध)"),
                    ("warn", "⏱️", "2–3 हफ़्ते", "फूल के बाद गेंदें दिखती हैं"),
                    ("", "🛡️", "बूटिंग", "बचाव का असली समय")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-common", "धान का भाव")],

    "card": {
        "emoji": "🍄",
        "bg": "#fefce8",
        "accent": "#a16207",
        "tag": "धान · रोग",
        "tag_bg": "#fef9c3",
        "tag_color": "#a16207",
        "title": "धान में कंडुआ रोग — बाली में पीली गेंद दिखे तो क्या करें",
        "cats": "anaaj keet rog",
        "keywords": "धान dhan कंडुआ kandua false smut हल्दी रोग हरदिया पीली गेंद बाली लक्ष्मी रोग दवा",
    },

    "related": [
        (f"{SITE}/articles/dhan-jhonka-rog", "#2e7d32", "🌾", "धान · रोग",
         "धान का झोंका रोग — गर्दन ब्लास्ट की पहचान"),
        (f"{SITE}/articles/dhan-nami-mandi-rejection", "#0369a1", "💧", "धान · मंडी",
         "धान की नमी — ट्रॉली मंडी से क्यों लौटती है"),
        (f"{SITE}/articles/dhan-msp-sarkari-rate-2026-27", "#ca8a04", "💰", "धान · MSP",
         "धान का सरकारी रेट 2026-27"),
        (f"{SITE}/articles/beej-upchar-vidhi", "#15803d", "🌱", "बीज · उपचार",
         "बीज उपचार — बुवाई से पहले क्यों ज़रूरी"),
        (f"{SITE}/bhav/paddy-common", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "धान का आज का मंडी भाव — राज्यवार LIVE रेट"),
        (f"{SITE}/chat", "#2e7d32", "🤖", "AI · सहायता",
         "फसल की फोटो भेजें — AI से तुरंत पहचान"),
    ],
}
