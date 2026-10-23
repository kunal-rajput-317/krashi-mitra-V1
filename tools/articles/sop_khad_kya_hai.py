# -*- coding: utf-8 -*-
# ============================================================
# SOP खाद (सल्फेट ऑफ पोटाश) — क्या है, MOP से कब बेहतर
#
# Why this topic (GSC, 5–18 Oct 2026): "sop fertilizer", "sop khad kya hai",
# "sop khad", "mop and sop fertilizer" earn impressions at position 7–9 with
# zero clicks, all landing on mop-guide — which answers SOP in one table. The
# khad cluster is where the site ranks best, so a dedicated page is the cheap
# win. mop-guide gets an inbound link to this page.
#
# Sources:
#   · FCO-style specification (K2O ≥ 50%, S ≥ 17.5%, total Cl ≤ 2.5%,
#     Na as NaCl ≤ 2.0%, moisture ≤ 1.5%) — SPIC SOP-SG product sheet
#     (spic.in/productcms/spic-sop-sg) and Indian supplier listings citing FCO.
#   · NBS coverage — Lok Sabha replies list DAP, MOP, MAP, TSP, SSP, ammonium
#     sulphate and complex NPK grades; SOP is not on the list. The page says
#     "is not on the list", not "is never subsidised", and asks the reader to
#     check the dealer's bill.
#   · Price premium — Tata Chemicals release (SOP import price roughly 1.8×
#     MOP) and CRU's Jan 2026 specialty-potash briefing (SOP premia at record
#     highs). No rupee figure is printed: the MRP is set by the seller and moves.
#   · Chloride-sensitive crops (tobacco, fruit) — standard agronomy; MOP-guide
#     already tells UP farmers MOP is right for wheat/paddy/cane/potato, and
#     this page agrees with it.
# No dose anywhere (LEGAL_RULES §2): the amount comes from the Soil Health Card.
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
      दुकान पर पोटाश माँगने जाएँ तो दो बोरियाँ दिखती हैं — एक पर <strong>MOP</strong> लिखा है,
      दूसरी पर <strong>SOP</strong> या <strong>0-0-50</strong>। दूसरी बोरी काफ़ी महँगी है, और दुकानदार
      कहता है "यह ज़्यादा अच्छा पोटाश है"। तो क्या सच में SOP बेहतर है, और क्या आपको यही खरीदनी चाहिए?
    </p>
    <p>
      सीधा जवाब: <strong>गेहूँ, धान, गन्ना और मक्का जैसी ज़्यादातर फसलों के लिए MOP ही ठीक और सस्ता है।</strong>
      SOP का पैसा चार हालात में वसूल होता है — क्लोराइड से बिगड़ने वाली फसलें (तंबाकू, अंगूर जैसे फल),
      खारी या ऊसर ज़मीन, ड्रिप और पत्तियों पर छिड़काव, और जहाँ पोटाश के साथ गंधक भी चाहिए। इस लेख में यही
      फ़र्क साफ़-साफ़ समझाया गया है, ताकि आप ज़रूरत से महँगी खाद न खरीदें।
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
      <h2>SOP खाद क्या है?</h2>
    </div>
    <p>
      SOP का पूरा नाम है <strong>Sulphate of Potash</strong> — हिंदी में <strong>सल्फेट ऑफ पोटाश</strong> या
      <strong>पोटैशियम सल्फेट</strong>। रसायन की भाषा में यह K₂SO₄ है। इसमें दो काम की चीज़ें हैं:
      <strong>पोटाश (K)</strong> और <strong>गंधक (सल्फर, S)</strong>। MOP (म्यूरेट ऑफ पोटाश) में पोटाश के
      साथ क्लोराइड आता है; SOP में क्लोराइड की जगह गंधक आता है। पूरा फ़र्क इसी एक बात से निकलता है।
    </p>
    <p>
      भारत में बिकने वाली SOP को <strong>उर्वरक नियंत्रण आदेश (FCO)</strong> का मानक पूरा करना होता है।
      खाद कंपनियाँ अपने SOP के लिए यही मानक छापती हैं:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>तत्व</th><th>SOP में कितना (मानक)</th><th>मतलब</th></tr>
      </thead>
      <tbody>
        <tr><td>पोटाश (K₂O)</td><td>कम से कम <strong>50%</strong></td><td>मुख्य पोषक तत्व</td></tr>
        <tr><td>गंधक (S)</td><td>कम से कम <strong>17.5%</strong></td><td>मुफ़्त में मिलने वाला दूसरा तत्व</td></tr>
        <tr><td>कुल क्लोराइड (Cl)</td><td>अधिक से अधिक <strong>2.5%</strong></td><td>लगभग क्लोराइड-मुक्त</td></tr>
        <tr><td>सोडियम (NaCl के रूप में)</td><td>अधिक से अधिक <strong>2%</strong></td><td>नमक कम</td></tr>
        <tr><td>नमी</td><td>अधिक से अधिक <strong>1.5%</strong></td><td>सूखी, ढेले रहित खाद</td></tr>
      </tbody>
    </table>
    <p>SOP बाज़ार में दो रूपों में मिलती है:</p>
    <ul>
      <li><strong>दानेदार या पाउडर (मिट्टी वाली SOP):</strong> खेत में बुवाई के समय या पेड़ों के थाले में मिट्टी में मिलाने के लिए। कंपनियाँ इसे अक्सर "SG" (soil grade) लिखती हैं।</li>
      <li><strong>पानी में पूरी घुलने वाली SOP (0-0-50, WSF):</strong> ड्रिप सिंचाई (फर्टिगेशन) और पत्तियों पर छिड़काव के लिए। यह महीन सफ़ेद पाउडर होता है और मिट्टी वाली SOP से भी महँगा होता है।</li>
    </ul>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>"0-0-50" का मतलब:</strong> बोरी पर लिखे तीन अंक नाइट्रोजन–फॉस्फोरस–पोटाश का प्रतिशत हैं।
        यानी SOP में नाइट्रोजन शून्य, फॉस्फोरस शून्य और पोटाश 50%। इसी तरह MOP को "0-0-60" लिखा जाता है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- COMPARISON TABLE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📊</span>
      <h2>MOP और SOP में क्या फ़र्क है?</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>पहलू</th><th>MOP (म्यूरेट ऑफ पोटाश)</th><th>SOP (सल्फेट ऑफ पोटाश)</th></tr>
      </thead>
      <tbody>
        <tr><td>पोटाश (K₂O)</td><td class="healthy">60%</td><td>50%</td></tr>
        <tr><td>साथ में आने वाला तत्व</td><td class="diseased">क्लोराइड — लगभग 45–47%</td><td class="healthy">गंधक — 17.5% से ज़्यादा</td></tr>
        <tr><td>मिट्टी में नमक का असर (लवण सूचकांक)</td><td class="diseased">ज़्यादा</td><td class="healthy">MOP के आधे से भी कम</td></tr>
        <tr><td>सरकारी सब्सिडी (NBS)</td><td class="healthy">पोषक-आधारित सब्सिडी की सूची में है</td><td class="diseased">संसद में बताई गई NBS सूची में नहीं है</td></tr>
        <tr><td>दाम</td><td class="healthy">सस्ता</td><td class="diseased">काफ़ी महँगा — बाज़ार तय करता है</td></tr>
        <tr><td>रंग</td><td>लाल-गुलाबी या सफ़ेद दाने</td><td>सफ़ेद या हल्का भूरा-सफ़ेद</td></tr>
        <tr><td>ड्रिप / छिड़काव</td><td>ड्रिप में कभी-कभी, छिड़काव में नहीं</td><td class="healthy">0-0-50 ग्रेड दोनों में</td></tr>
        <tr><td>किसके लिए सही</td><td>गेहूँ, धान, गन्ना, मक्का, दलहन, ज़्यादातर सब्ज़ियाँ</td><td>तंबाकू, अंगूर, अनार, नींबू वर्गीय फल, स्ट्रॉबेरी, खारी ज़मीन</td></tr>
      </tbody>
    </table>
    <div class="tip-box tip">
      <span class="tip-icon">🧮</span>
      <div class="tip-content">
        <strong>पोटाश का हिसाब:</strong> SOP में पोटाश 50% है और MOP में 60%। इसलिए जितना पोटाश MOP की
        एक बोरी देती है, उतना पाने के लिए SOP <strong>लगभग 1.2 गुना</strong> लगती है। महँगी खाद और
        ज़्यादा मात्रा — दोनों जोड़कर ही असली ख़र्च की तुलना करें।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- WHY CHLORIDE MATTERS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧂</span>
      <h2>क्लोराइड से किन फसलों को नुकसान होता है?</h2>
    </div>
    <p>
      क्लोराइड पौधे के लिए थोड़ी मात्रा में ज़रूरी है, और गेहूँ-धान जैसी फसलें इसे आराम से झेल लेती हैं।
      पर कुछ फसलें <strong>क्लोराइड के प्रति संवेदनशील</strong> हैं — उनमें ज़्यादा क्लोराइड से गुणवत्ता
      गिरती है, भले पैदावार दिखे:
    </p>
    <ul>
      <li><strong>तंबाकू:</strong> पत्ती में क्लोराइड बढ़ने से पत्ती ठीक से नहीं जलती और उसकी गुणवत्ता गिरती है। इसलिए तंबाकू में पोटाश के लिए SOP ही दी जाती है।</li>
      <li><strong>अंगूर, अनार और नींबू वर्गीय फल:</strong> क्लोराइड जमा होने से पत्तियों के किनारे झुलसते हैं। निर्यात वाले बागों में SOP आम है।</li>
      <li><strong>स्ट्रॉबेरी और कुछ फलियाँ:</strong> ये भी क्लोराइड से जल्दी प्रभावित होती हैं।</li>
      <li><strong>खारी (लवणीय) ज़मीन या खारा पानी:</strong> जहाँ मिट्टी या ट्यूबवेल के पानी में पहले से नमक है, वहाँ MOP का क्लोराइड नमक का बोझ और बढ़ाता है। ऐसी जगह SOP का कम लवण सूचकांक काम आता है।</li>
    </ul>
    <div class="tip-box info">
      <span class="tip-icon">🌾</span>
      <div class="tip-content">
        <strong>उत्तर भारत की मुख्य फसलों के लिए:</strong> गेहूँ, धान, गन्ना, मक्का और आलू में MOP ही
        सस्ता और पर्याप्त विकल्प है। इनमें SOP डालने से पैदावार उतनी नहीं बढ़ती कि दाम का फ़र्क निकल आए।
        MOP के बारे में पूरी जानकारी <a href="/articles/mop-guide">MOP खाद गाइड</a> में है।
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

  <!-- SULPHUR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🟡</span>
      <h2>गंधक का फ़ायदा — और सस्ते रास्ते</h2>
    </div>
    <p>
      SOP का दूसरा फ़ायदा है गंधक। सरसों, मूँगफली, सोयाबीन जैसी तिलहन फसलों और प्याज़-लहसुन को गंधक की ख़ास
      ज़रूरत होती है — तिलहन में तेल की मात्रा और प्याज़-लहसुन में तीखापन व भंडारण गंधक से जुड़े हैं। गंधक की
      कमी में नई पत्तियाँ पीली पड़ती हैं (नाइट्रोजन की कमी में पुरानी पत्तियाँ पहले पीली होती हैं)।
    </p>
    <p>
      पर <strong>अगर सिर्फ़ गंधक चाहिए, तो SOP सबसे महँगा रास्ता है।</strong> सस्ते विकल्प:
    </p>
    <ul>
      <li><strong>SSP (सिंगल सुपर फॉस्फेट):</strong> फॉस्फोरस के साथ लगभग 11% गंधक और कैल्शियम देती है, और सब्सिडी वाली खाद है। देखें <a href="/articles/ssp-khad-guide">SSP खाद गाइड</a>।</li>
      <li><strong>जिप्सम:</strong> गंधक और कैल्शियम दोनों, और ऊसर सुधार में भी काम आता है। देखें <a href="/articles/usar-bhumi-sudhar-jipsam">ऊसर भूमि सुधार</a>।</li>
      <li><strong>बेंटोनाइट सल्फर / अमोनियम सल्फेट:</strong> गंधक के दूसरे स्रोत — विस्तार <a href="/articles/sulphur-gandhak-ki-kami">गंधक की कमी</a> वाले लेख में है।</li>
    </ul>
    <p>
      यानी तिलहन के खेत में आम तौर पर <strong>MOP + SSP या जिप्सम</strong> का जोड़ SOP से सस्ता पड़ता है।
      SOP तब चुनें जब फसल क्लोराइड-संवेदनशील हो <em>और</em> गंधक भी चाहिए।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- WHEN AND HOW -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧪</span>
      <h2>SOP कब और कैसे डालें</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>तरीका</th><th>कौन सा ग्रेड</th><th>कब उपयुक्त</th></tr>
      </thead>
      <tbody>
        <tr><td>बुवाई / रोपाई के समय मिट्टी में</td><td>दानेदार / पाउडर (SG)</td><td>आख़िरी जुताई या कूँड़ में, बीज से थोड़ा हटकर</td></tr>
        <tr><td>फलदार पेड़ों के थाले में</td><td>दानेदार / पाउडर (SG)</td><td>बाग़ की ख़ुराक के समय, थाले की मिट्टी में मिलाकर, फिर सिंचाई</td></tr>
        <tr><td>ड्रिप से (फर्टिगेशन)</td><td>पानी में घुलने वाली 0-0-50</td><td>फूल आने के बाद फल बनने और भराव के समय, किस्तों में</td></tr>
        <tr><td>पत्तियों पर छिड़काव</td><td>सिर्फ़ 0-0-50 (WSF)</td><td>फल भराव के समय, कमी दिखने पर — घोल की ताक़त पैक के लेबल से</td></tr>
      </tbody>
    </table>
    <p><strong>कितनी खाद डालनी है, यह अपने खेत के मृदा स्वास्थ्य कार्ड (Soil Health Card) की सिफ़ारिश से तय करें, या अपने KVK / कृषि विभाग से पूछें।</strong> पोटाश की ज़रूरत मिट्टी जाँच से ही पता चलती है — कई खेतों में पोटाश पहले से पर्याप्त होता है। मिट्टी जाँच का तरीका <a href="/articles/mitti-jaanch-soil-health-card">मृदा स्वास्थ्य कार्ड</a> वाले लेख में है।</p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        <strong>दाम और सब्सिडी ख़ुद जाँचें:</strong> SOP का दाम विक्रेता तय करता है और समय के साथ बदलता है —
        इस लेख में कोई दाम नहीं दिया गया है। सब्सिडी की सूची भी सरकार बदल सकती है। ख़रीदने से पहले दुकान पर
        बोरी का MRP देखें, पक्का बिल लें, और अपनी फसल के लिए SOP सच में चाहिए या नहीं, यह अपने KVK या कृषि
        विभाग से पूछें। राज्यों की सिफ़ारिशें अलग-अलग होती हैं।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- IDENTIFY GENUINE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔎</span>
      <h2>असली SOP कैसे पहचानें</h2>
    </div>
    <ul>
      <li><strong>बोरी पर छपाई:</strong> "Sulphate of Potash" या "Potassium Sulphate", K₂O और गंधक का प्रतिशत, बनाने या आयात करने वाली कंपनी का नाम-पता, बैच नंबर, निर्माण की तारीख़ और MRP — ये सब होना चाहिए।</li>
      <li><strong>रंग:</strong> सफ़ेद या हल्का भूरा-सफ़ेद। लाल-गुलाबी दाने MOP के होते हैं, SOP के नहीं।</li>
      <li><strong>पानी में घोलकर देखें:</strong> 0-0-50 ग्रेड साफ़ पानी में पूरी तरह घुल जाना चाहिए; नीचे रेत या मिट्टी बैठे तो शक करें। दानेदार SOP धीरे घुलती है, यह सामान्य है।</li>
      <li><strong>खुली खाद न लें:</strong> बिना छपी बोरी या "पोटाश जैसी" खुली खाद में पोटाश का प्रतिशत कोई नहीं बता सकता।</li>
      <li><strong>शक हो तो:</strong> नमूना ज़िले की खाद परीक्षण प्रयोगशाला या कृषि विभाग को दिखाएँ और बिल संभालकर रखें।</li>
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
      <li><strong>हर फसल में SOP को "बढ़िया पोटाश" समझना</strong> — गेहूँ-धान में इससे ख़र्च बढ़ता है, पैदावार उतनी नहीं।</li>
      <li><strong>दानेदार SOP को ड्रिप में डालना</strong> — यह पूरी नहीं घुलती और ड्रिपर जाम कर सकती है। ड्रिप के लिए सिर्फ़ 0-0-50 ग्रेड।</li>
      <li><strong>मिट्टी वाली SOP का पत्तियों पर छिड़काव</strong> — अघुलनशील कण नोज़ल बंद करते हैं और पत्ती पर दाग़ छोड़ सकते हैं।</li>
      <li><strong>सिर्फ़ गंधक के लिए SOP ख़रीदना</strong> — SSP या जिप्सम से वही गंधक सस्ता मिलता है।</li>
      <li><strong>MOP और SOP दोनों एक साथ पूरी मात्रा में डालना</strong> — पोटाश दोगुना हो जाता है। दोनों का कुल पोटाश मिट्टी जाँच की सिफ़ारिश के अंदर रहे।</li>
      <li><strong>तेज़ धूप में ज़्यादा गाढ़ा घोल छिड़कना</strong> — पत्तियाँ झुलस सकती हैं। छिड़काव सुबह या शाम, लेबल की ताक़त पर।</li>
      <li><strong>बिना बिल के ख़रीदना</strong> — नकली खाद की शिकायत बिल के बिना नहीं हो पाती।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- DECISION TABLE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>आपके खेत के लिए कौन सा पोटाश?</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>आपकी हालत</th><th>सही चुनाव</th></tr></thead>
      <tbody>
        <tr><td>गेहूँ, धान, गन्ना, मक्का, आलू — सामान्य मिट्टी</td><td>MOP</td></tr>
        <tr><td>सरसों, मूँगफली, सोयाबीन — गंधक भी चाहिए</td><td>MOP + SSP या जिप्सम</td></tr>
        <tr><td>प्याज़, लहसुन</td><td>MOP + गंधक का स्रोत; खारी ज़मीन हो तो SOP पर विचार</td></tr>
        <tr><td>तंबाकू</td><td>SOP</td></tr>
        <tr><td>अंगूर, अनार, नींबू वर्गीय फल, स्ट्रॉबेरी</td><td>SOP (ख़ासकर फल भराव के समय)</td></tr>
        <tr><td>ड्रिप से सब्ज़ी / फल (टमाटर, शिमला मिर्च, केला आदि)</td><td>पानी में घुलने वाली 0-0-50 SOP, या घुलनशील पोटाश का दूसरा ग्रेड</td></tr>
        <tr><td>खारी (लवणीय) ज़मीन या खारा ट्यूबवेल पानी</td><td>SOP — साथ में ज़मीन सुधार की सलाह KVK से</td></tr>
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
      तीन बातें याद रखें। पहली — <strong>SOP में पोटाश 50% और गंधक 17.5% है, क्लोराइड लगभग नहीं</strong>।
      दूसरी — <strong>गेहूँ, धान, गन्ना जैसी मुख्य फसलों में MOP ही सस्ता और काफ़ी है</strong>; SOP
      तंबाकू, फलों, खारी ज़मीन और ड्रिप के लिए है। तीसरी — <strong>मात्रा मृदा स्वास्थ्य कार्ड से तय करें</strong>,
      दुकानदार की सलाह से नहीं।
    </p>
    <p><strong>महँगी खाद तभी फ़ायदे की है जब फसल को उसकी ज़रूरत हो।</strong></p>
  </section>
"""

FAQS = [
    ("SOP खाद क्या है?",
     "SOP यानी <strong>सल्फेट ऑफ पोटाश (पोटैशियम सल्फेट)</strong> — एक पोटाश खाद जिसमें कम से कम 50% पोटाश (K₂O) और 17.5% गंधक होता है, और क्लोराइड 2.5% से कम। इसे 0-0-50 भी लिखा जाता है।"),
    ("MOP और SOP में क्या अंतर है?",
     "MOP में <strong>60% पोटाश के साथ लगभग 45–47% क्लोराइड</strong> होता है, जबकि SOP में 50% पोटाश के साथ 17.5% गंधक और लगभग शून्य क्लोराइड। MOP सस्ता है और ज़्यादातर फसलों के लिए ठीक; SOP महँगी है और क्लोराइड-संवेदनशील फसलों व खारी ज़मीन के लिए।"),
    ("SOP का पूरा नाम क्या है?",
     "SOP का पूरा नाम <strong>Sulphate of Potash</strong> है, हिंदी में सल्फेट ऑफ पोटाश या पोटैशियम सल्फेट। रासायनिक सूत्र K₂SO₄ है।"),
    ("SOP खाद किस फसल में डालें?",
     "SOP सबसे ज़्यादा <strong>तंबाकू, अंगूर, अनार, नींबू वर्गीय फल और स्ट्रॉबेरी</strong> में फ़ायदेमंद है, क्योंकि इनकी गुणवत्ता क्लोराइड से गिरती है। खारी ज़मीन और ड्रिप सिंचाई में भी SOP अच्छा विकल्प है।"),
    ("क्या गेहूँ और धान में SOP डालना चाहिए?",
     "आम तौर पर नहीं — <strong>गेहूँ, धान, गन्ना और मक्का में MOP ही सस्ता और पर्याप्त है</strong>। इन फसलों में SOP से पैदावार इतनी नहीं बढ़ती कि उसका ज़्यादा दाम निकल आए।"),
    ("SOP पर सब्सिडी मिलती है क्या?",
     "संसद में बताई गई <strong>पोषक-आधारित सब्सिडी (NBS) की सूची में MOP है, SOP नहीं</strong>, इसलिए SOP का दाम बाज़ार तय करता है और यह MOP से काफ़ी महँगी पड़ती है। ताज़ा दाम और सब्सिडी के लिए बोरी का MRP और दुकान का बिल देखें।"),
    ("0-0-50 खाद क्या है?",
     "0-0-50 का मतलब है <strong>नाइट्रोजन 0%, फॉस्फोरस 0% और पोटाश 50%</strong> — यानी SOP। बाज़ार में यह नाम ज़्यादातर पानी में पूरी घुलने वाली SOP के लिए इस्तेमाल होता है, जो ड्रिप और पत्तियों पर छिड़काव के काम आती है।"),
    ("SOP का छिड़काव कब करें?",
     "SOP का छिड़काव <strong>फल भराव के समय</strong> या पोटाश की कमी दिखने पर, सिर्फ़ पानी में घुलने वाले 0-0-50 ग्रेड से करें। घोल की ताक़त पैक के लेबल से लें, और छिड़काव सुबह या शाम करें।"),
]

ARTICLE = {
    "slug": "sop-khad-kya-hai",
    "date": "2026-10-21",
    "date_label": "अक्टूबर 2026",
    "read_time": 9,
    "word_count": 2100,
    "lang": "hi",

    "section": "खाद व उर्वरक",
    "cat_label": "खाद व उर्वरक",
    "cat_query": "khad",
    "breadcrumb_leaf": "SOP खाद",

    "title": "SOP खाद क्या है? सल्फेट ऑफ पोटाश — MOP से कब बेहतर",
    "description": "SOP में 50% पोटाश, 17.5% गंधक और क्लोराइड 2.5% से कम। किन फसलों में MOP की जगह SOP दें, कहाँ नहीं — 0-0-50, दाम और पूरी तुलना।",
    "keywords": "SOP खाद, sop khad kya hai, sop fertilizer, सल्फेट ऑफ पोटाश, sulphate of potash, पोटैशियम सल्फेट, potassium sulphate, 0-0-50, MOP vs SOP, mop aur sop me antar, sop khad ke fayde, पोटाश खाद",

    "og_title": "SOP खाद क्या है — MOP से कब बेहतर, कब नहीं | KrashiMitra.in",
    "og_desc": "महँगा पोटाश हर फसल के लिए नहीं। किन फसलों में SOP का पैसा वसूल होता है, और कहाँ MOP ही काफ़ी है।",

    "hero_image": ("images/articles/sop-khad-kya-hai.webp",
                   "आंध्र प्रदेश के नेल्लोर ज़िले में खेत में सूखने के लिए टाँगी गई तंबाकू की पत्तियाँ",
                   "नेल्लोर (आंध्र प्रदेश) के खेत में सूखती तंबाकू की पत्तियाँ। तस्वीर में खाद नहीं, फसल है — तंबाकू क्लोराइड से सबसे ज़्यादा बिगड़ने वाली फसलों में है, इसीलिए इसमें पोटाश SOP से दिया जाता है।"),

    "headline": "SOP खाद क्या है — सल्फेट ऑफ पोटाश और MOP में अंतर, कब कौन सा डालें",
    "headline_en": "Sulphate of Potash (SOP) Fertiliser — What It Is and When It Beats MOP",
    "schema_desc": "SOP (सल्फेट ऑफ पोटाश) खाद की पूरी जानकारी: FCO मानक के अनुसार पोटाश व गंधक की मात्रा, MOP से तुलना, क्लोराइड-संवेदनशील फसलें, 0-0-50 ग्रेड, डालने का समय, असली SOP की पहचान और आम गलतियाँ।",
    "schema_keywords": ["SOP खाद", "सल्फेट ऑफ पोटाश", "sulphate of potash", "MOP vs SOP", "0-0-50"],

    "h1": "SOP खाद क्या है — MOP से कब बेहतर, कब नहीं",
    "h1_en": "Sulphate of Potash (SOP) vs Muriate of Potash (MOP)",
    "share_title": "SOP खाद क्या है? MOP और SOP में अंतर — किस फसल में कौन सा पोटाश",
    "hero_excerpt": "दुकान पर SOP की बोरी MOP से काफ़ी महँगी मिलती है। गेहूँ-धान में यह पैसा वापस नहीं आता — पर तंबाकू, फलों और खारी ज़मीन में यही सही पोटाश है।",
    "lede_h2": "SOP खाद — एक नज़र में",

    "badges": [("badge-season", "🧪 पोटाश 50% + गंधक 17.5%"),
               ("badge-disease", "🧂 क्लोराइड 2.5% से कम"),
               ("badge-location", "📍 पूरे भारत के लिए")],

    "quick_facts": [("", "🧪", "50%", "पोटाश (K₂O)"),
                    ("warn", "🟡", "17.5%", "गंधक"),
                    ("danger", "🧂", "≤ 2.5%", "क्लोराइड")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("grapes", "अंगूर का भाव"), ("tobacco", "तंबाकू का भाव"),
                   ("onion", "प्याज़ का भाव")],

    "card": {
        "emoji": "🧪",
        "bg": "#f5f3ff",
        "accent": "#7c3aed",
        "tag": "खाद · पोटाश",
        "tag_bg": "#ede9fe",
        "tag_color": "#6d28d9",
        "title": "SOP खाद क्या है — MOP से कब बेहतर, कब नहीं",
        "cats": "khad",
        "keywords": "SOP sop सल्फेट ऑफ पोटाश sulphate of potash पोटैशियम सल्फेट 0-0-50 MOP पोटाश गंधक तंबाकू अंगूर खारी",
    },

    "related": [
        (f"{SITE}/articles/mop-guide", "#b91c1c", "🔴", "खाद · पोटाश",
         "MOP खाद क्या है — पोटाश कब और कैसे डालें"),
        (f"{SITE}/articles/sulphur-gandhak-ki-kami", "#ca8a04", "🟡", "खाद · गंधक",
         "गंधक की कमी — पहचान और सस्ते उपाय"),
        (f"{SITE}/articles/ssp-khad-guide", "#1b7a3d", "⚪", "खाद · फॉस्फोरस",
         "SSP खाद — DAP से कब बेहतर"),
        (f"{SITE}/articles/mitti-jaanch-soil-health-card", "#a16207", "🧪", "मिट्टी · जाँच",
         "मिट्टी जाँच और मृदा स्वास्थ्य कार्ड"),
        (f"{SITE}/bhav/grapes", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "अंगूर का आज का मंडी भाव — राज्यवार LIVE रेट"),
        (f"{SITE}/chat", "#2e7d32", "🤖", "AI · सहायता",
         "खाद या फसल की फोटो भेजें — AI से सलाह"),
    ],
}
