# -*- coding: utf-8 -*-
# ============================================================
# धान का सरकारी रेट (MSP) 2026-27 — the national answer page. Written 6 Oct 2026.
#
# Why: Search Console (19 Sep – 2 Oct 2026) showed ~1,260 impressions a
# fortnight for state-less rate queries — "dhan ka sarkari rate 2026",
# "dhan ka msp 2026 27", "धान का समर्थन मूल्य 2026 27" — landing on the UP
# registration guide at position 5–9 and converting at ~1%. The UP page is a
# process page; this one answers the number.
#
# Sources (read 5–6 Oct 2026):
#   • KMS 2026-27 MSP: common ₹2,441, Grade A ₹2,461, both +₹72 — CCEA
#     13 May 2026 (PIB PRID 2260617), reported identically by Outlook Business,
#     S&P Global, Basis Point. 1.5× cost policy of Budget 2018-19: same release.
#   • Common-paddy series 2018-19 … 2025-26 (1,750 / 1,815 / 1,868 / 1,940 /
#     2,040 / 2,183 / 2,300 / 2,369): DES (desagri.gov.in) MSP statement, RBI
#     Handbook table, Agrospectrum 2025-26 report — all agree.
#   • Grade A 2023-24 … 2025-26 (2,203 / 2,320 / 2,389): DES Hindi MSP
#     statement. Grade A sits exactly ₹20 above common in all four years.
#   • State facts are the ones already sourced in each state's own module
#     (up_dhan_kharid_panjikaran, mp_e_uparjan_panjiyan, haryana_dhan_kharid,
#     punjab_dhan_kharid, chhattisgarh_dhan_kharidi, bihar_dhan_adhiprapti).
#   • Odisha: Samruddha Krushak Yojana, MSP + state input assistance paid to a
#     total of ₹3,100/q; KMS 2026-27 registration extended to 7 Sep — CMO
#     Odisha / Organiser, 5 Sep 2026.
#   • Telangana: ₹500/q bonus on fine (sanna) paddy from kharif 2024 — state
#     cabinet decision, Deccan Chronicle / The Week.
#
# Deliberately NOT claimed: any state's 2026-27 bonus amount that was not
# announced, any procurement quantity cap, any advice to sell or hold
# (LEGAL_RULES §1 — prices are information only), any basmati price.
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
      इस सीज़न किसान सबसे ज़्यादा एक ही सवाल पूछ रहे हैं: <strong>धान का सरकारी रेट कितना है?</strong> सीधा जवाब है — खरीफ विपणन वर्ष <strong>2026-27</strong> में सामान्य (कॉमन) धान का न्यूनतम समर्थन मूल्य <strong>₹2,441 प्रति क्विंटल</strong> और ग्रेड A धान का <strong>₹2,461 प्रति क्विंटल</strong> है। दोनों पिछले साल से <strong>₹72</strong> ज़्यादा हैं।
    </p>
    <p>
      पर यह रेट अपने-आप नहीं मिलता। यह उस धान का भाव है जो <strong>सरकारी खरीद केंद्र</strong> पर, <strong>पंजीकरण के बाद</strong>, और <strong>नमी व गुणवत्ता की शर्त</strong> पूरी करके बिकता है। इस लेख में पूरा हिसाब एक जगह है: 1 किलो से 100 क्विंटल तक कितना पैसा बनता है, 2018 से अब तक रेट कैसे बढ़ा, ग्रेड A क्या होता है, किस राज्य में पंजीकरण कहाँ होता है, और कौन-से राज्य MSP के ऊपर अपनी तरफ़ से पैसा देते हैं।
    </p>
    <div class="tip-box info">
      <span class="tip-icon">💡</span>
      <div class="tip-content">
        <strong>"2026-27" का मतलब:</strong> धान का MSP <strong>खरीफ विपणन वर्ष</strong> (KMS) के नाम से घोषित होता है — यानी जिस साल फसल बिकती है। अक्टूबर 2026 से सितंबर 2027 तक सरकारी केंद्रों पर बिकने वाला धान इसी "2026-27" रेट पर खरीदा जाता है।
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

  <!-- THE RATE -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">💰</span>
      <h2>धान का सरकारी रेट 2026-27 — एक नज़र में</h2>
    </div>
    <p>
      केंद्रीय मंत्रिमंडल की आर्थिक मामलों की समिति (CCEA) ने <strong>13 मई 2026</strong> को 14 खरीफ फसलों का नया MSP मंज़ूर किया। धान का रेट इस तरह है:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>श्रेणी</th><th>MSP 2026-27</th><th>MSP 2025-26</th><th>बढ़ोतरी</th></tr>
      </thead>
      <tbody>
        <tr><td>धान — सामान्य (कॉमन)</td><td><strong>₹2,441 / क्विंटल</strong></td><td>₹2,369</td><td>+₹72</td></tr>
        <tr><td>धान — ग्रेड A</td><td><strong>₹2,461 / क्विंटल</strong></td><td>₹2,389</td><td>+₹72</td></tr>
      </tbody>
    </table>
    <p>
      सरकार के अनुसार यह रेट 2018-19 के बजट में तय उस नियम पर बना है कि MSP पूरे देश की औसत उत्पादन लागत का <strong>कम से कम डेढ़ गुना</strong> हो। यही एक रेट पूरे देश में लागू होता है — उत्तर प्रदेश, पंजाब, छत्तीसगढ़ या बिहार, हर जगह केंद्र का MSP एक ही है। फ़र्क सिर्फ़ तब आता है जब कोई राज्य <strong>अपनी तरफ़ से बोनस</strong> जोड़ता है (नीचे अलग से दिया है)।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- RUPEES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🧮</span>
      <h2>किलो, मन और क्विंटल में — आपके धान का पूरा हिसाब</h2>
    </div>
    <p>
      एक क्विंटल = 100 किलो। गाँव में कई जगह भाव <strong>मन (40 किलो)</strong> में भी पूछा जाता है, इसलिए वह भी दिया है।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>मात्रा</th><th>सामान्य धान (₹2,441)</th><th>ग्रेड A धान (₹2,461)</th></tr>
      </thead>
      <tbody>
        <tr><td>1 किलो</td><td>₹24.41</td><td>₹24.61</td></tr>
        <tr><td>1 मन (40 किलो)</td><td>₹976.40</td><td>₹984.40</td></tr>
        <tr><td>1 क्विंटल</td><td>₹2,441</td><td>₹2,461</td></tr>
        <tr><td>10 क्विंटल</td><td>₹24,410</td><td>₹24,610</td></tr>
        <tr><td>25 क्विंटल</td><td>₹61,025</td><td>₹61,525</td></tr>
        <tr><td>50 क्विंटल</td><td>₹1,22,050</td><td>₹1,23,050</td></tr>
        <tr><td>100 क्विंटल</td><td>₹2,44,100</td><td>₹2,46,100</td></tr>
      </tbody>
    </table>
    <p>
      पिछले साल के मुक़ाबले बढ़ोतरी हर क्विंटल पर ₹72 है — यानी <strong>50 क्विंटल पर ₹3,600</strong> और <strong>100 क्विंटल पर ₹7,200</strong> ज़्यादा।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        यह तालिका सिर्फ़ गुणा-भाग है, किसी कमाई का वादा नहीं। असल रकम इस पर टिकी है कि केंद्र पर आपका धान <strong>कितना तौला गया</strong>, किस <strong>श्रेणी</strong> में दर्ज हुआ, और <strong>नमी व गुणवत्ता</strong> की जाँच में पास हुआ या नहीं।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- GRADE A VS COMMON -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🔍</span>
      <h2>ग्रेड A और सामान्य धान में क्या फ़र्क है?</h2>
    </div>
    <p>
      दोनों में सिर्फ़ <strong>₹20 प्रति क्विंटल</strong> का फ़र्क है, और पिछले चार साल से यही फ़र्क चल रहा है। श्रेणी दाने की बनावट से तय होती है — आमतौर पर <strong>पतला-लंबा दाना</strong> (लंबाई और चौड़ाई का अनुपात 2.5 या उससे ज़्यादा) ग्रेड A में गिना जाता है, और मोटा दाना सामान्य में।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>बिंदु</th><th>सामान्य (कॉमन)</th><th>ग्रेड A</th></tr>
      </thead>
      <tbody>
        <tr><td>MSP 2026-27</td><td>₹2,441</td><td>₹2,461</td></tr>
        <tr><td>दाना</td><td>मोटा या मध्यम</td><td>पतला और लंबा</td></tr>
        <tr><td>श्रेणी कौन तय करता है</td><td colspan="2">खरीद केंद्र पर खरीद करने वाला कर्मचारी, किस्म और दाना देखकर</td></tr>
        <tr><td>गुणवत्ता की शर्तें</td><td colspan="2">दोनों पर एक जैसी — नमी 17%, अपद्रव्य 1%-1%, क्षतिग्रस्त दाने 5%</td></tr>
      </tbody>
    </table>
    <div class="tip-box tip">
      <span class="tip-icon">🟡</span>
      <div class="tip-content">
        दोनों श्रेणियों में सबसे ज़्यादा धान <strong>नमी</strong> पर लौटता है, श्रेणी पर नहीं। सरकारी खरीद में धान की अधिकतम नमी <strong>17%</strong> है — सुखाने का पूरा तरीका <a href="https://krashimitra.in/articles/dhan-nami-mandi-rejection">धान में नमी 17% का पूरा नियम</a> में है।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- HISTORY -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">📈</span>
      <h2>2018 से अब तक धान का सरकारी रेट</h2>
    </div>
    <p>
      सामान्य धान का MSP 2018-19 में ₹1,750 था। आठ साल में यह <strong>₹691 बढ़कर ₹2,441</strong> हो गया है — लगभग 39% की बढ़ोतरी।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>खरीफ विपणन वर्ष</th><th>सामान्य धान (₹/क्विंटल)</th><th>पिछले साल से</th></tr>
      </thead>
      <tbody>
        <tr><td>2018-19</td><td>₹1,750</td><td>—</td></tr>
        <tr><td>2019-20</td><td>₹1,815</td><td>+₹65</td></tr>
        <tr><td>2020-21</td><td>₹1,868</td><td>+₹53</td></tr>
        <tr><td>2021-22</td><td>₹1,940</td><td>+₹72</td></tr>
        <tr><td>2022-23</td><td>₹2,040</td><td>+₹100</td></tr>
        <tr><td>2023-24</td><td>₹2,183</td><td>+₹143</td></tr>
        <tr><td>2024-25</td><td>₹2,300</td><td>+₹117</td></tr>
        <tr><td>2025-26</td><td>₹2,369</td><td>+₹69</td></tr>
        <tr><td><strong>2026-27</strong></td><td><strong>₹2,441</strong></td><td><strong>+₹72</strong></td></tr>
      </tbody>
    </table>
    <p>
      ग्रेड A धान का MSP 2023-24 में ₹2,203, 2024-25 में ₹2,320 और 2025-26 में ₹2,389 था — हर साल सामान्य धान से ठीक ₹20 ऊपर।
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

  <!-- WHERE YOU GET IT -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🏛️</span>
      <h2>सरकारी रेट मिलता कहाँ है? पंजीकरण के बिना नहीं</h2>
    </div>
    <p>
      MSP वह भाव है जिस पर <strong>सरकारी एजेंसियाँ</strong> धान खरीदती हैं। इसके लिए तीन शर्तें हैं:
    </p>
    <ol>
      <li><strong>पंजीकरण:</strong> अपने राज्य के खरीद पोर्टल पर समय रहते धान और रकबा दर्ज करना।</li>
      <li><strong>सरकारी केंद्र या मंडी:</strong> धान राज्य के क्रय केंद्र, समिति, पैक्स या अनाज मंडी में सरकारी खरीद के दौरान बेचना।</li>
      <li><strong>गुणवत्ता:</strong> नमी 17% तक और साफ़ धान।</li>
    </ol>
    <p>
      मंडी में निजी व्यापारी का भाव खुली बोली से तय होता है — वह MSP से ऊपर भी हो सकता है और नीचे भी। आज किस मंडी में कितना भाव चल रहा है, यह <a href="https://krashimitra.in/bhav/paddy-common">धान का आज का मंडी भाव</a> पर देखा जा सकता है।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- STATES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🗺️</span>
      <h2>राज्यवार — पंजीकरण कहाँ और खरीद कब</h2>
    </div>
    <p>
      MSP पूरे देश में एक है, पर पंजीकरण का पोर्टल और खरीद की तारीख़ हर राज्य अपनी तय करता है। हर राज्य की पूरी प्रक्रिया उसके अलग लेख में है:
    </p>
    <table class="article-table">
      <thead>
        <tr><th>राज्य</th><th>पंजीकरण कहाँ</th><th>2026-27 की स्थिति</th></tr>
      </thead>
      <tbody>
        <tr><td><a href="https://krashimitra.in/articles/up-dhan-kharid-panjikaran">उत्तर प्रदेश</a></td><td>fcs.up.gov.in या UP Kisan Mitra ऐप</td><td>पश्चिमी UP में 1 अक्टूबर से, पूर्वी UP में 1 नवंबर से (हर साल की क्रय नीति से तय)</td></tr>
        <tr><td><a href="https://krashimitra.in/articles/mp-e-uparjan-panjiyan">मध्य प्रदेश</a></td><td>ई-उपार्जन (mpeuparjan.nic.in)</td><td>पंजीयन 15 सितंबर से 10 अक्टूबर 2026 तक</td></tr>
        <tr><td><a href="https://krashimitra.in/articles/haryana-dhan-kharid">हरियाणा</a></td><td>मेरी फसल मेरा ब्यौरा (fasal.haryana.gov.in)</td><td>मंडियों में तुलाई 24 सितंबर 2026 से</td></tr>
        <tr><td><a href="https://krashimitra.in/articles/punjab-dhan-kharid">पंजाब</a></td><td>अनाज खरीद पोर्टल (anaajkharid.in)</td><td>सरकारी खरीद 1 अक्टूबर 2026 से</td></tr>
        <tr><td><a href="https://krashimitra.in/articles/chhattisgarh-dhan-kharidi">छत्तीसगढ़</a></td><td>एग्री स्टैक पंजीयन + समिति</td><td>एग्री स्टैक पंजीयन 31 अक्टूबर 2026 तक ज़रूरी</td></tr>
        <tr><td><a href="https://krashimitra.in/articles/bihar-dhan-adhiprapti">बिहार</a></td><td>कृषि विभाग किसान निबंधन, फिर सहकारिता विभाग पर आवेदन</td><td>पैक्स / व्यापार मंडल पर बिक्री</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        तारीख़ें राज्य सरकार के आदेश से तय होती हैं और आगे-पीछे हो सकती हैं। अपने ज़िले की असली तारीख़ राज्य के खरीद पोर्टल, ज़िला खाद्य/विपणन अधिकारी या अपनी समिति से ज़रूर पुष्टि कर लीजिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- STATE BONUS -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">➕</span>
      <h2>किन राज्यों में MSP के ऊपर पैसा मिलता है?</h2>
    </div>
    <p>
      कुछ राज्य केंद्र के MSP के ऊपर अपनी तरफ़ से बोनस या "आदान सहायता" देते हैं। इसीलिए कई किसान "धान का रेट ₹3,100" सुनते हैं — वह MSP नहीं, MSP और राज्य की सहायता का जोड़ है।
    </p>
    <table class="article-table">
      <thead>
        <tr><th>राज्य</th><th>योजना</th><th>क्या मिलता है</th></tr>
      </thead>
      <tbody>
        <tr><td>छत्तीसगढ़</td><td>कृषक उन्नति योजना</td><td>पिछले सीज़न (2025-26) MSP और आदान सहायता मिलाकर कुल ₹3,100 प्रति क्विंटल। 2026-27 की दर अभी घोषित होनी है।</td></tr>
        <tr><td>ओडिशा</td><td>समृद्ध कृषक योजना</td><td>MSP के ऊपर राज्य की इनपुट सहायता, कुल ₹3,100 प्रति क्विंटल तक</td></tr>
        <tr><td>तेलंगाना</td><td>पतले धान पर बोनस</td><td>खरीफ 2024 से पतली (सन्ना) किस्मों पर ₹500 प्रति क्विंटल बोनस</td></tr>
      </tbody>
    </table>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        बोनस हर सीज़न राज्य सरकार नए सिरे से तय करती है — पिछले साल मिला था, इसका मतलब यह नहीं कि इस साल भी उतना ही मिलेगा। जिन राज्यों के नाम यहाँ नहीं हैं, वहाँ इस सीज़न का कोई बोनस हमें सरकारी स्रोत में नहीं मिला। अपने राज्य के खाद्य विभाग की वेबसाइट पर ताज़ा आदेश देखिए।
      </div>
    </div>
  </section>

  <hr class="section-divider" />

  <!-- BASMATI -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🌾</span>
      <h2>बासमती धान का सरकारी रेट क्यों नहीं होता?</h2>
    </div>
    <p>
      <strong>बासमती धान MSP पर नहीं खरीदा जाता।</strong> सरकारी खरीद का धान राशन (PDS) के चावल में जाता है, और बासमती उस व्यवस्था में नहीं है। बासमती मंडी में <strong>खुली बोली</strong> पर निजी व्यापारी और निर्यातक खरीदते हैं — इसलिए 1509, 1121, 1718 या 1692 का भाव रोज़ बदलता है और किस्म के हिसाब से अलग होता है।
    </p>
    <p>
      किस बासमती किस्म में क्या फ़र्क है और मंडी का भाव कहाँ देखें, यह <a href="https://krashimitra.in/articles/basmati-dhan-kisme-1509-1692-1718">1509, 1692, 1718 और 1121 धान — बासमती किस्मों का पूरा फ़र्क</a> में है। आज का भाव <a href="https://krashimitra.in/bhav/paddy-basmati">बासमती धान का मंडी भाव</a> पर।
    </p>
  </section>

  <hr class="section-divider" />

  <!-- MISTAKES -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">🚫</span>
      <h2>ये गलतियाँ न करें</h2>
    </div>
    <ul>
      <li><strong>पंजीकरण को बाद के लिए टालना:</strong> MSP पर बिक्री पंजीकरण से ही खुलती है, और तारीख़ निकलने के बाद पोर्टल दोबारा खुले, इसकी कोई गारंटी नहीं।</li>
      <li><strong>राज्य के बोनस को MSP समझना:</strong> ₹3,100 जैसी दर किसी एक राज्य की योजना की है, पूरे देश का सरकारी रेट नहीं।</li>
      <li><strong>गीला धान लेकर केंद्र पहुँचना:</strong> 17% से ज़्यादा नमी पर धान लौटा दिया जाता है।</li>
      <li><strong>बासमती को MSP की लाइन में लगाना:</strong> बासमती सरकारी केंद्र पर नहीं, खुली बोली में बिकता है।</li>
      <li><strong>बिना पर्ची के बेचना:</strong> सरकारी खरीद की तौल-पर्ची या रसीद ही भुगतान और शिकायत का सबूत है।</li>
      <li><strong>"पक्का रेट दिलाने" वाले दलाल को पैसे देना:</strong> MSP का पैसा सीधे आपके बैंक खाते में आता है, किसी बिचौलिये के ज़रिए नहीं।</li>
    </ul>
  </section>

  <hr class="section-divider" />

  <!-- CONCLUSION -->
  <section class="article-section">
    <div class="section-heading">
      <span class="s-icon">✅</span>
      <h2>निष्कर्ष</h2>
    </div>
    <p>
      2026-27 में धान का सरकारी रेट <strong>सामान्य ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल</strong> है — पूरे देश में एक। यह रेट सरकारी केंद्र पर, पंजीकरण के बाद, सूखे और साफ़ धान पर मिलता है। कुछ राज्य इसके ऊपर अपना बोनस जोड़ते हैं, और बासमती इस व्यवस्था से बाहर है।
    </p>
    <p>
      अपने राज्य का लेख खोलकर पंजीकरण की स्थिति देख लीजिए, और बेचने से पहले मंडी का आज का भाव भी देखिए — फ़ैसला आपका है।
    </p>
    <div class="tip-box warning">
      <span class="tip-icon">⚠️</span>
      <div class="tip-content">
        यह लेख सामान्य जानकारी के लिए है। समर्थन मूल्य केंद्र सरकार और बोनस व तारीख़ें राज्य सरकारें तय करती हैं, और ये बदलते रहते हैं। KrashiMitra एक निजी वेबसाइट है — न सरकारी एजेंट, न किसी का पंजीकरण करता है, न फसल खरीदता या बिकवाता है। अंतिम पुष्टि हमेशा अपने राज्य के खरीद पोर्टल, खरीद केंद्र या ज़िला अधिकारी से ही कीजिए।
      </div>
    </div>
  </section>
"""

FAQS = [
    ("धान का सरकारी रेट 2026-27 कितना है?",
     "खरीफ विपणन वर्ष 2026-27 में धान का सरकारी रेट (MSP) <strong>सामान्य ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल</strong> है, जो पिछले साल से ₹72 ज़्यादा है। यह रेट सरकारी खरीद केंद्र पर पंजीकरण के बाद मिलता है।"),
    ("1 किलो धान का सरकारी रेट कितना है?",
     "2026-27 में सामान्य धान का सरकारी रेट <strong>₹24.41 प्रति किलो</strong> और ग्रेड A का <strong>₹24.61 प्रति किलो</strong> है। एक मन (40 किलो) सामान्य धान ₹976.40 का बनता है।"),
    ("2025-26 में धान का MSP कितना था?",
     "2025-26 में धान का MSP <strong>सामान्य ₹2,369 और ग्रेड A ₹2,389 प्रति क्विंटल</strong> था। 2026-27 में दोनों ₹72 बढ़कर ₹2,441 और ₹2,461 हो गए।"),
    ("ग्रेड A और सामान्य धान में क्या फ़र्क है?",
     "ग्रेड A धान का MSP सामान्य से <strong>₹20 प्रति क्विंटल ज़्यादा</strong> है। आमतौर पर पतला-लंबा दाना ग्रेड A में और मोटा दाना सामान्य में गिना जाता है; श्रेणी खरीद केंद्र पर कर्मचारी तय करता है।"),
    ("बासमती धान का सरकारी रेट कितना है?",
     "<strong>बासमती धान का कोई सरकारी रेट (MSP) नहीं है</strong> — वह सरकारी केंद्रों पर नहीं खरीदा जाता। बासमती मंडी में खुली बोली पर बिकता है और उसका भाव किस्म व दिन के हिसाब से बदलता है।"),
    ("धान का रेट ₹3,100 कहाँ मिलता है?",
     "₹3,100 प्रति क्विंटल <strong>केंद्र का MSP नहीं, बल्कि MSP और राज्य की सहायता का जोड़</strong> है — छत्तीसगढ़ में पिछले सीज़न और ओडिशा में यही कुल दर रही। बोनस हर सीज़न राज्य सरकार नए सिरे से तय करती है।"),
    ("क्या मंडी में व्यापारी को धान MSP पर खरीदना ज़रूरी है?",
     "MSP <strong>सरकारी खरीद की दर</strong> है; मंडी में निजी व्यापारी का भाव खुली बोली से तय होता है और MSP से ऊपर या नीचे हो सकता है। MSP पाने के लिए पंजीकरण कराकर सरकारी केंद्र पर बेचना होता है।"),
    ("सरकारी रेट पर धान बेचने के लिए पंजीकरण कहाँ होता है?",
     "पंजीकरण <strong>हर राज्य के अपने पोर्टल</strong> पर होता है — UP में fcs.up.gov.in, MP में ई-उपार्जन, हरियाणा में मेरी फसल मेरा ब्यौरा, पंजाब में अनाज खरीद पोर्टल। तारीख़ें राज्य तय करता है, इसलिए समय रहते पंजीकरण कर लीजिए।"),
]

ARTICLE = {
    "slug": "dhan-msp-sarkari-rate-2026-27",
    "date": "2026-10-06",
    "date_label": "अक्टूबर 2026",
    "read_time": 8,
    "word_count": 2000,
    "lang": "hi",

    "section": "मंडी व MSP",
    "cat_label": "मंडी व MSP",
    "cat_query": "jankari",
    "breadcrumb_leaf": "धान MSP 2026-27",

    "title": "Dhan ka Sarkari Rate 2026-27: धान MSP ₹2,441, ग्रेड A ₹2,461",
    "description": "धान का सरकारी रेट 2026-27: सामान्य ₹2,441, ग्रेड A ₹2,461 प्रति क्विंटल (+₹72)। 1 किलो ₹24.41। 2018 से अब तक के रेट, 100 क्विंटल का हिसाब और राज्यवार खरीद।",
    "keywords": "धान का सरकारी रेट 2026, dhan ka sarkari rate 2026-27, dhan ka msp 2026 27, धान का समर्थन मूल्य 2026-27, paddy msp 2026-27, धान MSP 2441, grade a paddy msp 2461, dhan ka rate sarkari, धान का रेट 2026, 1 kg dhan ka sarkari rate",

    "og_title": "धान का सरकारी रेट 2026-27 — सामान्य ₹2,441, ग्रेड A ₹2,461 | KrashiMitra.in",
    "og_desc": "धान का MSP 2026-27, किलो से 100 क्विंटल तक का हिसाब, 2018 से अब तक के रेट और राज्यवार पंजीकरण।",
    "hero_image": ("images/articles/dhan-msp-sarkari-rate-2026-27.webp",
                   "खेत में पकती हुई धान की सुनहरी बालियाँ",
                   "खेत में पकती धान की बालियाँ — यही दाना सरकारी खरीद केंद्र पर समर्थन मूल्य पर बिकता है।"),
    "headline": "धान का सरकारी रेट 2026-27: MSP ₹2,441, ग्रेड A ₹2,461 — पूरा हिसाब",
    "headline_en": "Paddy MSP 2026-27: common ₹2,441, Grade A ₹2,461 — rate, history and states",
    "schema_desc": "खरीफ विपणन वर्ष 2026-27 में धान का न्यूनतम समर्थन मूल्य — सामान्य ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल; किलो से 100 क्विंटल तक का हिसाब, 2018-19 से अब तक का रेट, ग्रेड A का अर्थ, राज्यवार पंजीकरण और राज्यों का बोनस।",
    "schema_keywords": ["धान MSP 2026-27", "धान का सरकारी रेट", "paddy msp 2026-27",
                        "समर्थन मूल्य", "ग्रेड A धान"],

    "h1": "धान का सरकारी रेट 2026-27",
    "h1_en": "Paddy MSP 2026-27 — the Government Rate, Explained",
    "share_title": "धान का सरकारी रेट 2026-27: सामान्य ₹2,441, ग्रेड A ₹2,461 — किलो से क्विंटल तक हिसाब",
    "hero_excerpt": "सामान्य धान ₹2,441 और ग्रेड A ₹2,461 प्रति क्विंटल — पर यह रेट सरकारी केंद्र पर, पंजीकरण के बाद, सूखे धान पर ही मिलता है।",
    "lede_h2": "एक रेट, पूरे देश में — पर शर्तों के साथ",

    "badges": [("badge-location", "📍 पूरे भारत में लागू"),
               ("badge-season", "🗓️ खरीफ विपणन वर्ष 2026-27"),
               ("badge-disease", "📢 13 मई 2026 को घोषित")],

    "quick_facts": [("", "🌾", "₹2,441", "सामान्य धान का MSP / क्विंटल"),
                    ("warn", "⭐", "₹2,461", "ग्रेड A धान का MSP / क्विंटल"),
                    ("danger", "💧", "17%", "इससे ज़्यादा नमी पर धान नहीं बिकता")],

    "body": BODY,
    "faqs": FAQS,

    "bhav_links": [("paddy-common", "धान का भाव"),
                   ("paddy-basmati", "बासमती धान का भाव"),
                   ("rice", "चावल का भाव"),
                   ("wheat", "गेहूं का भाव")],

    "card": {
        "emoji": "🌾", "bg": "#fff9e6", "accent": "#ca8a04",
        "tag": "धान MSP 2026-27", "tag_bg": "#fff4e0", "tag_color": "#ca8a04",
        "title": "धान का सरकारी रेट 2026-27: सामान्य ₹2,441, ग्रेड A ₹2,461 — पूरा हिसाब",
        "cats": "jankari anaaj",
        "keywords": "dhan ka sarkari rate msp 2026-27 धान समर्थन मूल्य 2441 2461 grade a paddy msp किलो क्विंटल हिसाब राज्यवार बोनस",
    },

    "related": [
        (f"{SITE}/articles/up-dhan-kharid-panjikaran", "#0369a1", "🧾", "UP · धान खरीद",
         "UP धान खरीद पंजीकरण — MSP ₹2,441 पर धान बेचने की पूरी प्रक्रिया"),
        (f"{SITE}/articles/mp-e-uparjan-panjiyan", "#0369a1", "🧾", "MP · ई-उपार्जन",
         "MP ई-उपार्जन पंजीयन — समर्थन मूल्य पर फसल बेचने की प्रक्रिया"),
        (f"{SITE}/articles/basmati-dhan-kisme-1509-1692-1718", "#a16207", "🌾", "बासमती · किस्में",
         "1509, 1692, 1718, 1121 धान — बासमती किस्मों का पूरा फ़र्क"),
        (f"{SITE}/articles/dhan-nami-mandi-rejection", "#0f766e", "💧", "धान · गुणवत्ता",
         "धान में नमी कितनी होनी चाहिए? 17% का पूरा नियम"),
        (f"{SITE}/articles/rabi-msp-2027-28", "#ca8a04", "🌾", "रबी · MSP",
         "रबी MSP 2027-28 — गेहूं ₹2,610, सरसों ₹6,613"),
        (f"{SITE}/bhav/paddy-common", "#1b7a3d", "💰", "मंडी · आज के भाव",
         "धान का आज का मंडी भाव — राज्यवार LIVE रेट"),
    ],
}
