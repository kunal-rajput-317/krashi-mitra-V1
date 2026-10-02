# -*- coding: utf-8 -*-
# ============================================================
# रबी MSP 2027-28 — six mandated rabi crops, announced 30 Sep 2026.
#
# Sources (read 2 Oct 2026):
#   • CCEA decision, 30 Sep 2026, briefed by Ashwini Vaishnaw (PIB). Reported
#     identically by ANI / Business Standard / Punjab Kesari / Free Press Journal:
#     wheat 2,610 (+25), barley 2,286 (+136), gram 5,958 (+83),
#     lentil 7,390 (+390), rapeseed-mustard 6,613 (+413), safflower 7,215 (+675).
#     Margin over all-India weighted average cost: 106 / 58 / 59 / 92 / 96 / 50 %.
#     Estimated outgo ₹90,962 crore for RMS 2027-28.
#   • RMS 2026-27 (Oct 2025 CCEA): wheat 2,585, barley 2,150, gram 5,875,
#     lentil 7,000, mustard 6,200, safflower 6,540 — every 2027-28 figure minus
#     its increase reproduces these, so the two tables agree.
#
# Deliberately NOT claimed: procurement dates or quantities for 2027, any state
# bonus for 2027, any reason for the small wheat increase, any advice to sell or
# hold (LEGAL_RULES §1 — prices are information only).
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
      रबी की बुवाई शुरू होने से ठीक पहले सरकार ने <strong>रबी विपणन सत्र 2027-28 का न्यूनतम समर्थन मूल्य (MSP)</strong> तय कर दिया है। केंद्रीय मंत्रिमंडल की आर्थिक मामलों की समिति (CCEA) ने <strong>30 सितंबर 2026</strong> को छह रबी फसलों — गेहूं, जौ, चना, मसूर, सरसों और कुसुम — का नया MSP मंज़ूर किया।
    </p>
    <p>
      इस बार की सबसे बड़ी ख़बर दो उल्टी दिशाओं में है। <strong>गेहूं का MSP सिर्फ़ ₹25 बढ़कर ₹2,610 प्रति क्विंटल</strong> हुआ है — यानी 1% से भी कम। वहीं <strong>सरसों पर ₹413, मसूर पर ₹390 और कुसुम पर ₹675</strong> की बढ़ोतरी हुई है। जो फसल आप अभी अक्टूबर–नवंबर 2026 में बोएँगे, वही मार्च–जून 2027 में इन्हीं दरों पर बिकने के लिए मंडी पहुँचेगी। इस लेख में पूरी तालिका है, 10 क्विंटल पर असल में कितना फ़र्क पड़ता है उसका हिसाब है, और यह भी कि MSP का मतलब क्या है और क्या नहीं।
    </p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>"2027-28" नाम से भ्रम न हो।</strong> रबी का MSP <strong>विपणन सत्र</strong> (marketing season) के नाम से घोषित होता है, यानी जिस साल फसल बिकेगी। अभी बोया जाने वाला गेहूं अप्रैल 2027 के आसपास बिकेगा, इसलिए उसका MSP "2027-28" कहलाता है।
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
      <h2>रबी MSP 2027-28 — छह फसलों की पूरी तालिका</h2>
    </div>
    <p>सभी दरें <strong>रुपये प्रति क्विंटल</strong> में हैं। पिछले साल (2026-27) की दर साथ में दी है ताकि बढ़ोतरी साफ़ दिखे।</p>
    <table class="article-table">
      <thead>
        <tr><th>फसल</th><th>MSP 2026-27</th><th>MSP 2027-28</th><th>बढ़ोतरी</th><th>बढ़ोतरी %</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>गेहूं</strong></td><td>₹2,585</td><td class="healthy"><strong>₹2,610</strong></td><td class="diseased">+₹25</td><td>लगभग 1%</td></tr>
        <tr><td><strong>जौ</strong></td><td>₹2,150</td><td class="healthy"><strong>₹2,286</strong></td><td>+₹136</td><td>लगभग 6.3%</td></tr>
        <tr><td><strong>चना</strong></td><td>₹5,875</td><td class="healthy"><strong>₹5,958</strong></td><td class="diseased">+₹83</td><td>लगभग 1.4%</td></tr>
        <tr><td><strong>मसूर</strong></td><td>₹7,000</td><td class="healthy"><strong>₹7,390</strong></td><td>+₹390</td><td>लगभग 5.6%</td></tr>
        <tr><td><strong>सरसों / तोरिया</strong></td><td>₹6,200</td><td class="healthy"><strong>₹6,613</strong></td><td>+₹413</td><td>लगभग 6.7%</td></tr>
        <tr><td><strong>कुसुम (safflower)</strong></td><td>₹6,540</td><td class="healthy"><strong>₹7,215</strong></td><td>+₹675</td><td>लगभग 10.3%</td></tr>
      </tbody>
    </table>
    <p>
      सरकार के अनुमान के मुताबिक़ इन दरों पर रबी विपणन सत्र 2027-28 में किसानों को कुल <strong>लगभग ₹90,962 करोड़</strong> का भुगतान होगा। यह सरकार का अनुमान है, किसी किसान को मिलने वाली रकम का वादा नहीं।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        ये आँकड़े केंद्रीय मंत्रिमंडल के 30 सितंबर 2026 के फ़ैसले से लिए गए हैं। आधिकारिक प्रेस विज्ञप्ति <a href="https://pib.gov.in" target="_blank" rel="noopener">pib.gov.in</a> पर देखें। <strong>KrashiMitra एक निजी वेबसाइट है</strong>, सरकार की नहीं, और हम कोई ख़रीद या पंजीकरण नहीं करते।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- WHAT THE NUMBERS MEAN ON 10 QUINTAL -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧮</span>
      <h2>10 क्विंटल पर असल फ़र्क कितना?</h2>
    </div>
    <p>
      प्रतिशत से बात समझ नहीं आती, रुपये से आती है। मान लीजिए आप किसी एक फसल के <strong>10 क्विंटल</strong> MSP पर बेचते हैं। पिछले साल और इस साल की दर पर रकम ऐसे बदलती है:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>फसल (10 क्विंटल)</th><th>2026-27 की दर पर</th><th>2027-28 की दर पर</th><th>ज़्यादा मिलेगा</th></tr>
      </thead>
      <tbody>
        <tr><td>गेहूं</td><td>₹25,850</td><td>₹26,100</td><td class="diseased">₹250</td></tr>
        <tr><td>जौ</td><td>₹21,500</td><td>₹22,860</td><td>₹1,360</td></tr>
        <tr><td>चना</td><td>₹58,750</td><td>₹59,580</td><td class="diseased">₹830</td></tr>
        <tr><td>मसूर</td><td>₹70,000</td><td>₹73,900</td><td class="healthy">₹3,900</td></tr>
        <tr><td>सरसों</td><td>₹62,000</td><td>₹66,130</td><td class="healthy">₹4,130</td></tr>
        <tr><td>कुसुम</td><td>₹65,400</td><td>₹72,150</td><td class="healthy">₹6,750</td></tr>
      </tbody>
    </table>
    <p>
      यानी <strong>गेहूं के 10 क्विंटल पर सिर्फ़ ₹250 ज़्यादा</strong>, जबकि <strong>सरसों के 10 क्विंटल पर ₹4,130 ज़्यादा</strong>। अपनी उपज के क्विंटल से इसी तरह गुणा करके आप अपना हिसाब निकाल सकते हैं: <strong>बढ़ोतरी × आपके क्विंटल</strong>।
    </p>
    <div class="tip-box tip">
      <span class="tip-icon">✍️</span>
      <div class="tip-content">
        <strong>एक उदाहरण:</strong> जिस किसान ने पिछले साल 40 क्विंटल गेहूं सरकारी केंद्र पर बेचा, उसे उतनी ही उपज पर इस बार कुल <strong>₹1,000</strong> ज़्यादा मिलेंगे (40 × ₹25)। जो 8 क्विंटल सरसों बेचता है, उसे <strong>₹3,304</strong> ज़्यादा (8 × ₹413)।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- MARGIN OVER COST -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📐</span>
      <h2>लागत पर मार्जिन — "106%" का मतलब क्या है?</h2>
    </div>
    <p>
      सरकार हर MSP के साथ बताती है कि यह दर <strong>पूरे देश की औसत उत्पादन लागत से कितने प्रतिशत ऊपर</strong> है। 2018-19 के बजट में तय हुआ था कि MSP कम से कम लागत का डेढ़ गुना (यानी 50% मार्जिन) होगा। इस बार के मार्जिन:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>फसल</th><th>लागत पर मार्जिन</th><th>इसका मतलब (लगभग)</th></tr>
      </thead>
      <tbody>
        <tr><td>गेहूं</td><td class="healthy">106%</td><td>MSP औसत लागत का लगभग दोगुना</td></tr>
        <tr><td>सरसों</td><td class="healthy">96%</td><td>लगभग दोगुना</td></tr>
        <tr><td>मसूर</td><td class="healthy">92%</td><td>लगभग दोगुना से थोड़ा कम</td></tr>
        <tr><td>चना</td><td>59%</td><td>लगभग 1.6 गुना</td></tr>
        <tr><td>जौ</td><td>58%</td><td>लगभग 1.6 गुना</td></tr>
        <tr><td>कुसुम</td><td>50%</td><td>ठीक डेढ़ गुना</td></tr>
      </tbody>
    </table>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>यह लागत आपके खेत की नहीं, पूरे देश का भारित औसत है।</strong> इसमें बीज, खाद, सिंचाई, मज़दूरी, किराया-मशीन और परिवार के श्रम का अनुमानित मूल्य जुड़ता है। जिस किसान की ज़मीन ठेके की है, या डीज़ल से सिंचाई होती है, उसकी असली लागत इससे काफ़ी ज़्यादा हो सकती है। इसलिए "106% मार्जिन" को अपने मुनाफ़े का अनुमान न मानें — अपनी लागत का हिसाब अलग से रखें।
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

  <!-- WHAT MSP IS AND IS NOT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔍</span>
      <h2>MSP क्या है — और क्या नहीं</h2>
    </div>
    <p>
      MSP वह दर है जिस पर <strong>सरकारी एजेंसी (जैसे FCI, राज्य की ख़रीद एजेंसियाँ, NAFED) ख़रीद केंद्र पर फसल ख़रीदती है</strong>। बहुत से किसान इसे "मंडी का न्यूनतम भाव" समझ लेते हैं, और वहीं से नुकसान शुरू होता है।
    </p>
    <ul>
      <li><strong>MSP सरकारी ख़रीद की दर है:</strong> निजी व्यापारी पर MSP पर ख़रीदने की कोई केंद्रीय कानूनी बाध्यता नहीं है। इसलिए मंडी में खुली बोली का भाव MSP से नीचे या ऊपर, दोनों हो सकता है।</li>
      <li><strong>ख़रीद हर फसल की हर जगह नहीं होती:</strong> गेहूं की सरकारी ख़रीद पंजाब, हरियाणा, मध्य प्रदेश, उत्तर प्रदेश, राजस्थान जैसे राज्यों में बड़े पैमाने पर होती है। चना, मसूर और सरसों की ख़रीद आमतौर पर तभी और वहीं होती है जहाँ राज्य सरकार इसकी माँग करे, और मात्रा की सीमा भी होती है।</li>
      <li><strong>पंजीकरण पहले, बिक्री बाद में:</strong> ज़्यादातर राज्यों में सरकारी केंद्र पर बेचने के लिए किसान को पहले ऑनलाइन पंजीकरण कराना पड़ता है। पंजीकरण की खिड़की आमतौर पर फसल आने से कुछ हफ़्ते पहले खुलती है।</li>
      <li><strong>गुणवत्ता की शर्त (FAQ — Fair Average Quality):</strong> सरकारी केंद्र पर फसल तय मानक (नमी, टूटे दाने, मिट्टी-कचरा) के अंदर होनी चाहिए। गीली या गंदी फसल लौटाई जा सकती है।</li>
    </ul>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        2027 की ख़रीद की तारीख़ें, पंजीकरण की आख़िरी तिथि और कोई राज्य-स्तरीय बोनस <strong>अभी घोषित नहीं हुए हैं</strong>। ये हर राज्य अलग तय करता है। अपने ज़िले के खाद्य विभाग, मंडी समिति या राज्य के ख़रीद पोर्टल से ही पुष्टि करें।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- MSP vs MANDI -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">⚖️</span>
      <h2>सरकारी केंद्र बनाम खुली मंडी — तुलना</h2>
    </div>
    <table class="article-table">
      <thead>
        <tr><th>बात</th><th>✅ सरकारी ख़रीद केंद्र (MSP)</th><th>🏪 खुली मंडी / व्यापारी</th></tr>
      </thead>
      <tbody>
        <tr><td>भाव</td><td class="healthy">तय — MSP (और कहीं-कहीं राज्य का बोनस)</td><td>रोज़ बदलता है; MSP से नीचे भी, ऊपर भी</td></tr>
        <tr><td>पंजीकरण</td><td>ज़रूरी, पहले से</td><td>आमतौर पर ज़रूरी नहीं</td></tr>
        <tr><td>गुणवत्ता जाँच</td><td class="diseased">सख़्त — नमी और सफ़ाई का मानक</td><td>भाव में कटौती करके ले लेते हैं</td></tr>
        <tr><td>भुगतान</td><td>सीधे बैंक खाते में, कुछ दिनों में</td><td>नकद या जल्दी, पर शर्तें व्यापारी की</td></tr>
        <tr><td>किन फसलों पर</td><td>मुख्यतः गेहूं; बाकी राज्य और साल पर निर्भर</td><td>सभी फसलें</td></tr>
        <tr><td>इंतज़ार</td><td class="diseased">टोकन / बारी का इंतज़ार हो सकता है</td><td>आमतौर पर उसी दिन</td></tr>
      </tbody>
    </table>
    <p>
      कौन सा रास्ता बेहतर है, यह आपके राज्य, आपकी फसल और उस दिन के मंडी भाव पर निर्भर करता है। आज के भाव देखने के लिए KrashiMitra पर <a href="/bhav/wheat">गेहूं का मंडी भाव</a> और <a href="/bhav/mustard">सरसों का मंडी भाव</a> देखें — ये भाव सिर्फ़ जानकारी के लिए हैं, ख़रीद-बिक्री की सलाह नहीं।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- CROP CHOICE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🌱</span>
      <h2>क्या MSP देखकर फसल बदलनी चाहिए?</h2>
    </div>
    <p>
      सरसों और मसूर पर बड़ी बढ़ोतरी देखकर बहुत से किसान सोचेंगे कि गेहूं की जगह सरसों बो दें। फ़ैसला सिर्फ़ MSP से न करें — इन बातों को साथ तौलें:
    </p>
    <ul>
      <li><strong>पानी:</strong> गेहूं को आमतौर पर पाँच-छह सिंचाई चाहिए, सरसों और चना कम पानी में हो जाते हैं। जिनके पास पानी कम है, उनके लिए यह MSP से बड़ा कारण है।</li>
      <li><strong>ख़रीद की पक्की व्यवस्था:</strong> गेहूं की सरकारी ख़रीद का ढाँचा सबसे बड़ा है। सरसों-चना-मसूर की सरकारी ख़रीद सीमित रहती है, इसलिए अक्सर खुली मंडी पर निर्भर रहना पड़ता है।</li>
      <li><strong>बुवाई का समय:</strong> सिंचित सरसों की बुवाई अक्टूबर में होती है, गेहूं की नवंबर में। जो खेत धान से देर से खाली होता है, उसमें सरसों का समय निकल चुका हो सकता है।</li>
      <li><strong>फसल चक्र:</strong> चना और मसूर दलहन हैं, ये मिट्टी के लिए अच्छे माने जाते हैं। हर साल एक ही फसल से मिट्टी थकती है।</li>
      <li><strong>जोखिम:</strong> पाला, माहू और सफ़ेद रतुआ सरसों के बड़े ख़तरे हैं; चने में फली छेदक। हर फसल का अपना जोखिम है।</li>
    </ul>
    <p>
      हर फसल की बुवाई, किस्म और कैलेंडर के लिए हमारी गाइड देखें: <a href="/articles/gehun-unnat-kheti">गेहूं की उन्नत खेती</a>, <a href="/articles/sarson-ki-unnat-kheti">सरसों की उन्नत खेती</a>, <a href="/articles/chana-ki-kheti">चने की खेती</a>, <a href="/articles/masoor-ki-kheti">मसूर की खेती</a> और <a href="/articles/jau-ki-kheti">जौ की खेती</a>।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- MISTAKES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚫</span>
      <h2>ये गलतियाँ कभी न करें</h2>
    </div>
    <ul>
      <li><strong>MSP को मंडी का पक्का भाव मान लेना</strong> — व्यापारी MSP से कम दे सकता है। सरकारी केंद्र पर ही MSP मिलता है।</li>
      <li><strong>पंजीकरण की तारीख़ भूल जाना</strong> — पंजीकरण नहीं तो सरकारी केंद्र पर बिक्री नहीं। रबी की कटाई से पहले अपने राज्य का पोर्टल देखते रहें।</li>
      <li><strong>गीली फसल लेकर केंद्र पहुँचना</strong> — नमी ज़्यादा होने पर फसल लौट सकती है या कटौती हो सकती है। सुखाकर, साफ़ करके ले जाएँ।</li>
      <li><strong>किसी "एजेंट" को पैसे देकर पंजीकरण कराना</strong> — पंजीकरण सरकारी पोर्टल, CSC या ख़रीद केंद्र पर होता है। जो MSP पर बिकवाने के नाम पर पैसे माँगे, उससे बचें।</li>
      <li><strong>दूसरे के नाम पर अपनी फसल बेचना</strong> — ज़मीन के रिकॉर्ड और बैंक खाते में नाम मेल खाना चाहिए; ग़लत नाम पर भुगतान अटकता है।</li>
      <li><strong>व्हाट्सऐप पर आए "नए MSP" पर भरोसा</strong> — हर साल फ़र्ज़ी तालिकाएँ घूमती हैं। ऊपर की तालिका 30 सितंबर 2026 के कैबिनेट फ़ैसले की है; शक हो तो pib.gov.in पर मिलाएँ।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CALENDAR -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗓️</span>
      <h2>रबी 2026-27 — बुवाई से बिक्री तक का कैलेंडर</h2>
    </div>
    <table class="article-table">
      <thead><tr><th>समय</th><th>क्या होता है / आपको क्या करना है</th></tr></thead>
      <tbody>
        <tr><td>30 सितंबर 2026</td><td>रबी MSP 2027-28 घोषित (ऊपर की तालिका)</td></tr>
        <tr><td>अक्टूबर 2026</td><td>सरसों, तोरिया, चना, मसूर की बुवाई का समय (क्षेत्र के अनुसार)</td></tr>
        <tr><td>नवंबर 2026</td><td>गेहूं और जौ की बुवाई का मुख्य समय</td></tr>
        <tr><td>दिसंबर 2026 – फ़रवरी 2027</td><td>सिंचाई, निगरानी; ज़मीन के रिकॉर्ड, बैंक खाता और आधार-लिंक की जाँच करा लें</td></tr>
        <tr><td>आमतौर पर फ़रवरी – मार्च 2027</td><td>राज्यों के ख़रीद पोर्टल पर पंजीकरण खुलता है (तारीख़ राज्य घोषित करेगा)</td></tr>
        <tr><td>आमतौर पर मार्च – जून 2027</td><td>सरसों, चना, गेहूं की आवक और सरकारी ख़रीद (राज्य की घोषणा के अनुसार)</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        "आमतौर पर" वाली तारीख़ें पिछले सालों के ढर्रे पर हैं, 2027 की घोषणा नहीं। आपके राज्य की सही तारीख़ ज़िला खाद्य एवं आपूर्ति विभाग या मंडी समिति बताएगी।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- CONCLUSION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✅</span>
      <h2>निष्कर्ष</h2>
    </div>
    <p>
      तीन बातें याद रखें। पहली, <strong>गेहूं का MSP ₹2,610 है — बढ़ोतरी सिर्फ़ ₹25</strong>, यानी 10 क्विंटल पर ₹250। दूसरी, <strong>सरसों (₹6,613), मसूर (₹7,390) और कुसुम (₹7,215) पर इस बार सबसे ज़्यादा बढ़ोतरी</strong> हुई है। तीसरी, <strong>MSP सिर्फ़ सरकारी केंद्र पर मिलता है, और उसके लिए पंजीकरण पहले कराना पड़ता है</strong>।
    </p>
    <p><strong>फसल अपने खेत, पानी और बाज़ार देखकर चुनें — MSP सिर्फ़ उस फ़ैसले का एक हिस्सा है।</strong></p>
  </section>
"""

FAQS = [
    ("गेहूं का MSP 2027 में कितना है?",
     "रबी विपणन सत्र 2027-28 के लिए गेहूं का MSP <strong>₹2,610 प्रति क्विंटल</strong> है, जो पिछले साल के ₹2,585 से ₹25 ज़्यादा है। यह दर अक्टूबर–नवंबर 2026 में बोए जाने वाले और 2027 में बिकने वाले गेहूं पर लागू होगी।"),
    ("सरसों का नया MSP कितना है?",
     "सरसों (rapeseed-mustard) का MSP 2027-28 के लिए <strong>₹6,613 प्रति क्विंटल</strong> है, यानी पिछले साल के ₹6,200 से ₹413 ज़्यादा। सरकार के अनुसार यह औसत उत्पादन लागत पर लगभग 96% मार्जिन है।"),
    ("चना और मसूर का MSP 2027-28 कितना है?",
     "चने का MSP <strong>₹5,958</strong> (₹83 बढ़ा) और मसूर का MSP <strong>₹7,390</strong> (₹390 बढ़ा) प्रति क्विंटल है। दोनों दरें 30 सितंबर 2026 को कैबिनेट ने मंज़ूर कीं।"),
    ("रबी MSP 2027-28 में सबसे ज़्यादा किस फसल का बढ़ा?",
     "सबसे ज़्यादा बढ़ोतरी <strong>कुसुम (safflower) पर ₹675</strong> प्रति क्विंटल की हुई, जिससे इसका MSP ₹7,215 हो गया। इसके बाद सरसों (₹413) और मसूर (₹390) हैं; सबसे कम गेहूं (₹25) पर।"),
    ("क्या मंडी में व्यापारी को MSP पर ही खरीदना पड़ता है?",
     "नहीं, MSP <strong>सरकारी ख़रीद केंद्र की दर</strong> है; निजी व्यापारी पर इसे देने की कोई केंद्रीय कानूनी बाध्यता नहीं है। इसलिए मंडी का भाव MSP से नीचे या ऊपर दोनों हो सकता है।"),
    ("MSP पर गेहूं बेचने के लिए पंजीकरण कब होगा?",
     "2027 के पंजीकरण की तारीख़ अभी घोषित नहीं हुई है; पिछले सालों में ज़्यादातर राज्यों ने <strong>फ़रवरी–मार्च</strong> के आसपास पोर्टल खोला। अपने राज्य के ख़रीद पोर्टल, CSC या ज़िला खाद्य विभाग से तारीख़ की पुष्टि करें।"),
    ("जौ का MSP 2027-28 कितना है?",
     "जौ का MSP <strong>₹2,286 प्रति क्विंटल</strong> है, जो पिछले साल के ₹2,150 से ₹136 ज़्यादा है। सरकार के अनुसार यह लागत पर लगभग 58% मार्जिन है।"),
]

ARTICLE = {
    "slug": "rabi-msp-2027-28",
    "date": "2026-10-02",
    "date_label": "अक्टूबर 2026",
    "read_time": 8,
    "word_count": 2100,
    "lang": "hi",

    "section": "मंडी व MSP",
    "cat_label": "मंडी व MSP",
    "cat_query": "jankari",
    "breadcrumb_leaf": "रबी MSP 2027-28",

    "title": "रबी MSP 2027-28: गेहूं ₹2,610, सरसों ₹6,613 — 6 फसलों के नए रेट",
    "description": "गेहूं का MSP सिर्फ़ ₹25 बढ़कर ₹2,610, सरसों ₹413 बढ़कर ₹6,613, मसूर ₹7,390, चना ₹5,958। 30 सितंबर 2026 का कैबिनेट फ़ैसला — पूरी तालिका और 10 क्विंटल का हिसाब।",
    "keywords": "रबी MSP 2027-28, गेहूं MSP 2027, सरसों MSP, चना MSP, मसूर MSP, जौ MSP, gehu msp 2027, sarso msp 2027-28, rabi msp 2027-28, wheat msp 2610, minimum support price rabi",

    "og_title": "रबी MSP 2027-28 — गेहूं ₹2,610, सरसों ₹6,613 | KrashiMitra.in",
    "og_desc": "छह रबी फसलों का नया MSP, पिछले साल से तुलना और 10 क्विंटल पर असल फ़र्क।",

    "hero_image": ("images/articles/rabi-msp-2027-28.webp",
                   "हिमाचल प्रदेश में सीढ़ीदार खेतों में उगता हरा गेहूं",
                   "हिमाचल प्रदेश के मंडी ज़िले के एक गाँव में सीढ़ीदार खेतों में गेहूं की फसल।"),

    "headline": "रबी MSP 2027-28: गेहूं ₹2,610, सरसों ₹6,613 — छह फसलों की पूरी तालिका",
    "headline_en": "Rabi MSP 2027-28: wheat ₹2,610, mustard ₹6,613 — all six crops",
    "schema_desc": "30 सितंबर 2026 को घोषित रबी विपणन सत्र 2027-28 का MSP — गेहूं, जौ, चना, मसूर, सरसों, कुसुम; पिछले साल से तुलना, लागत पर मार्जिन और 10 क्विंटल का हिसाब।",
    "schema_keywords": ["रबी MSP 2027-28", "गेहूं MSP", "सरसों MSP", "rabi msp 2027-28", "wheat msp"],

    "h1": "रबी MSP 2027-28 — छह फसलों के नए रेट",
    "h1_en": "Rabi MSP 2027-28 — new support prices for six crops",
    "share_title": "रबी MSP 2027-28: गेहूं ₹2,610 (+₹25), सरसों ₹6,613 (+₹413) — पूरी तालिका",
    "hero_excerpt": "गेहूं का MSP सिर्फ़ ₹25 बढ़ा, सरसों का ₹413 और कुसुम का ₹675। अभी बोई जाने वाली फसल 2027 में इन्हीं दरों पर सरकारी केंद्र पर बिकेगी।",
    "lede_h2": "रबी MSP 2027-28 एक नज़र में",

    "badges": [("badge-disease", "📢 30 सितंबर 2026 को घोषित"),
               ("badge-season", "🗓️ रबी विपणन सत्र 2027-28"),
               ("badge-location", "📍 पूरे भारत में")],

    "quick_facts": [("", "🌾", "₹2,610", "गेहूं का MSP / क्विंटल"),
                    ("danger", "📉", "+₹25", "गेहूं पर बढ़ोतरी — 1% से कम"),
                    ("warn", "📈", "+₹675", "कुसुम — सबसे बड़ी बढ़ोतरी")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("wheat", "गेहूं का भाव"), ("mustard", "सरसों का भाव"),
                   ("bengal-gram-gram-whole", "चने का भाव"),
                   ("lentil-masur-whole", "मसूर का भाव"), ("barley-jau", "जौ का भाव")],

    "card": {
        "emoji": "🌾",
        "bg": "#fff9e6",
        "accent": "#ca8a04",
        "tag": "MSP 2027-28",
        "tag_bg": "#fff4e0",
        "tag_color": "#ca8a04",
        "title": "रबी MSP 2027-28: गेहूं ₹2,610, सरसों ₹6,613 — छह फसलों के नए रेट",
        "cats": "jankari anaaj",
        "keywords": "msp 2027-28 rabi gehu sarso chana masoor jau kusum minimum support price",
    },

    "related": [
        (f"{SITE}/articles/gehun-unnat-kheti", "#ca8a04", "🌾", "गेहूं · बुवाई",
         "गेहूं की उन्नत खेती — बुवाई 1–25 नवंबर, नई किस्में"),
        (f"{SITE}/articles/sarson-ki-unnat-kheti", "#ca8a04", "🌼", "सरसों · बुवाई",
         "सरसों की उन्नत खेती — बुवाई 10–25 अक्टूबर"),
        (f"{SITE}/articles/chana-ki-kheti", "#7c5c2a", "🫘", "चना · खेती",
         "चने की खेती — बुवाई, किस्में और कैलेंडर"),
        (f"{SITE}/articles/enam-online-fasal-bechna", "#1b7a3d", "🏪", "मंडी · e-NAM",
         "e-NAM पर फसल ऑनलाइन कैसे बेचें"),
        (f"{SITE}/bhav/wheat", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "गेहूं का आज का मंडी भाव — राज्यवार LIVE रेट"),
        (f"{SITE}/chat", "#2e7d32", "🤖", "AI · सहायता",
         "फसल की फोटो भेजें — AI से तुरंत पहचान व इलाज"),
    ],
}
