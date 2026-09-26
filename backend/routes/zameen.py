"""ज़मीन इकाई कैलकुलेटर — /bigha-calculator.

A farmer asking "1 बीघा में कितने एकड़" gets a different answer in every state,
because बीघा is not one unit: Uttar Pradesh's पक्का बीघा is almost twice West
Bengal's. This page converts between the land units a farmer actually uses,
with the state chosen first so बीघा/बिस्वा/कट्ठा mean what they mean there.

One table (UNITS / STATES below) feeds both the server-rendered reference table
and the in-page converter, so the two can never give different answers.

Honesty rules for this page:
* Only the metric/imperial units (वर्ग फुट, एकड़, हेक्टेयर…) are exact. Every
  state बीघा is the figure commonly used in that state, labelled अनुमानित, and
  the page tells the farmer to confirm with the लेखपाल / पटवारी / तहसील for a
  registry or खतौनी. A state whose बीघा we could not pin to one figure is left
  out rather than guessed; the "आपके इलाके का बीघा" field covers it.
* No personal data, no location, no storage — the arithmetic runs in the page.
"""

import json
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend.routes.bhav import SITE, _crumb_ld, _doc, _faq, _ld

router = APIRouter()

CANON = f"{SITE}/bigha-calculator"

SQFT = 0.09290304          # m² in one square foot — exact by definition
ACRE = 4046.8564224        # m² in one acre (43,560 sq ft) — exact

# key → (Hindi name, English name, m²). Exact units, used in every state.
UNITS = {
    "sqft":    ("वर्ग फुट",  "sq ft",    SQFT),
    "sqm":     ("वर्ग मीटर", "sq m",     1.0),
    "gaj":     ("गज (वर्ग गज)", "sq yard", 9 * SQFT),
    "decimal": ("डिसमिल",    "decimal",  ACRE / 100),
    "guntha":  ("गुंठा",     "guntha",   ACRE / 40),
    "marla":   ("मरला",      "marla",    ACRE / 160),
    "kanal":   ("कनाल",      "kanal",    ACRE / 8),
    "acre":    ("एकड़",      "acre",     ACRE),
    "hectare": ("हेक्टेयर",  "hectare",  10000.0),
}

# State → its local units, largest first: (key, Hindi, English, sq ft).
# Sub-units are exact fractions of the state's बीघा (20 बिस्वा = 1 बीघा etc.);
# the बीघा itself is the commonly used figure and is labelled अनुमानित.
# `extra` lists which exact UNITS are also in everyday use there.
STATES = {
    "up": {
        "short": "यूपी, पक्का",
        "hi": "उत्तर प्रदेश (पक्का बीघा)", "en": "Uttar Pradesh",
        "local": [("bigha", "बीघा", "bigha", 27225.0),
                  ("biswa", "बिस्वा", "biswa", 27225.0 / 20),
                  ("biswansi", "बिस्वांसी", "biswansi", 27225.0 / 400)],
        "extra": ["acre", "hectare"],
        "note": "पश्चिमी यूपी के कई गाँवों में कच्चा बीघा चलता है, जो पक्के बीघे का "
                "लगभग एक-तिहाई होता है।",
    },
    "bihar": {
        "short": "बिहार",
        "hi": "बिहार", "en": "Bihar",
        "local": [("bigha", "बीघा", "bigha", 27220.0),
                  ("kattha", "कट्ठा", "kattha", 27220.0 / 20),
                  ("dhur", "धुर", "dhur", 27220.0 / 400)],
        "extra": ["decimal", "acre", "hectare"],
        "note": "",
    },
    "west-bengal": {
        "short": "बंगाल",
        "hi": "पश्चिम बंगाल", "en": "West Bengal",
        "local": [("bigha", "बीघा", "bigha", 14400.0),
                  ("kattha", "कट्ठा", "kattha", 14400.0 / 20),
                  ("chhatak", "छटाक", "chhatak", 14400.0 / 320)],
        "extra": ["decimal", "acre", "hectare"],
        "note": "",
    },
    "assam": {
        "short": "असम",
        "hi": "असम", "en": "Assam",
        "local": [("bigha", "बीघा", "bigha", 14400.0),
                  ("katha", "कठा", "katha", 14400.0 / 5),
                  ("lessa", "लेस्सा", "lessa", 14400.0 / 100)],
        "extra": ["acre", "hectare"],
        "note": "असम में 1 बीघा = 5 कठा होता है, बंगाल की तरह 20 नहीं।",
    },
    "rajasthan-pakka": {
        "short": "राजस्थान, पक्का",
        "hi": "राजस्थान (पक्का बीघा)", "en": "Rajasthan (pakka)",
        "local": [("bigha", "बीघा", "bigha", 27225.0),
                  ("biswa", "बिस्वा", "biswa", 27225.0 / 20)],
        "extra": ["acre", "hectare"],
        "note": "",
    },
    "rajasthan-kachcha": {
        "short": "राजस्थान, कच्चा",
        "hi": "राजस्थान (कच्चा बीघा)", "en": "Rajasthan (kachcha)",
        "local": [("bigha", "बीघा", "bigha", 17424.0),
                  ("biswa", "बिस्वा", "biswa", 17424.0 / 20)],
        "extra": ["acre", "hectare"],
        "note": "",
    },
    "gujarat": {
        "short": "गुजरात",
        "hi": "गुजरात", "en": "Gujarat",
        "local": [("bigha", "बीघा", "bigha", 17424.0)],
        "extra": ["guntha", "acre", "hectare"],
        "note": "गुजरात में 1 बीघा = 16 गुंठा माना जाता है; कुछ इलाकों में बीघा बड़ा होता है।",
    },
    "himachal": {
        "short": "हिमाचल",
        "hi": "हिमाचल प्रदेश", "en": "Himachal Pradesh",
        "local": [("bigha", "बीघा", "bigha", 8712.0),
                  ("biswa", "बिस्वा", "biswa", 8712.0 / 20)],
        "extra": ["acre", "hectare"],
        "note": "",
    },
    "punjab-haryana": {
        "short": "पंजाब/हरियाणा",
        "hi": "पंजाब / हरियाणा (किल्ला-कनाल)", "en": "Punjab / Haryana",
        "local": [],
        "extra": ["acre", "kanal", "marla", "hectare"],
        "note": "यहाँ 1 किल्ला = 1 एकड़ = 8 कनाल = 160 मरला।",
    },
    "maharashtra-karnataka": {
        "short": "महाराष्ट्र/कर्नाटक",
        "hi": "महाराष्ट्र / कर्नाटक (गुंठा)", "en": "Maharashtra / Karnataka",
        "local": [],
        "extra": ["acre", "guntha", "hectare"],
        "note": "1 एकड़ = 40 गुंठा।",
    },
}
DEFAULT_STATE = "up"


def to_sqm(value: float, unit: str, state: str = DEFAULT_STATE) -> float:
    """Area in m². `unit` is an exact UNITS key or one of `state`'s local units."""
    if unit in UNITS:
        return value * UNITS[unit][2]
    for key, _hi, _en, sqft in STATES[state]["local"]:
        if key == unit:
            return value * sqft * SQFT
    raise KeyError(unit)


def convert(value: float, src: str, dst: str, state: str = DEFAULT_STATE) -> float:
    return to_sqm(value, src, state) / to_sqm(1.0, dst, state)


def _num(x: float) -> str:
    """Indian digit grouping, few decimals for big numbers, more for small."""
    if x >= 100:
        return f"{x:,.0f}" if abs(x - round(x)) < 0.005 else f"{x:,.2f}"
    if x >= 1:
        return f"{x:,.2f}".rstrip("0").rstrip(".")
    return f"{x:.4f}".rstrip("0").rstrip(".")


def _state_table() -> str:
    """Reference table: one बीघा in each state, in acre / sq ft / m². Crawlable
    and works with JS off — the converter above it is the same numbers live."""
    rows = []
    for key, s in STATES.items():
        bigha = next((u for u in s["local"] if u[0] == "bigha"), None)
        if not bigha:
            continue
        sqft = bigha[3]
        rows.append(
            f"<tr><td>{escape(s['hi'])}</td>"
            f"<td>{_num(sqft)}</td>"
            f"<td>{_num(sqft * SQFT)}</td>"
            f"<td>{_num(sqft * SQFT / ACRE)}</td>"
            f"<td>{_num(ACRE / (sqft * SQFT))}</td></tr>")
    return ('<div class="zm-tablewrap"><table class="zm-table"><thead><tr>'
            '<th>राज्य</th><th>1 बीघा = वर्ग फुट</th><th>वर्ग मीटर</th>'
            '<th>एकड़</th><th>1 एकड़ = बीघा</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


# Exact units in the order a farmer reaches for them.
_COMMON = ["acre", "hectare", "sqft", "sqm", "gaj", "decimal", "guntha", "kanal", "marla"]
DEFAULT_FROM, DEFAULT_TO = "up:bigha", "acre"


def _flat_units() -> list:
    """Every unit the two pickers offer, as one flat list. A state unit's key is
    "state:unit" (up:bigha) so the same बीघा name can sit under each state."""
    out = [{"k": k, "hi": UNITS[k][0], "sqm": UNITS[k][2], "est": False,
            "grp": "", "note": ""} for k in _COMMON]
    for sk, s in STATES.items():
        for uk, hi, _en, sqft in s["local"]:
            out.append({"k": f"{sk}:{uk}", "hi": f"{hi} · {s['short']}",
                        "sqm": sqft * SQFT, "est": True, "grp": s["short"],
                        "note": s["note"]})
    return out


def _options(selected: str) -> str:
    """<option>s for one picker: exact units first, then one <optgroup> per state."""
    html, grp = [], ""
    for u in _flat_units():
        if u["grp"] != grp:
            if grp:
                html.append("</optgroup>")
            grp = u["grp"]
            html.append(f'<optgroup label="{escape(grp)} (अनुमानित)">')
        sel = " selected" if u["k"] == selected else ""
        html.append(f'<option value="{escape(u["k"])}"{sel}>{escape(u["hi"])}</option>')
    if grp:
        html.append("</optgroup>")
    return "".join(html)


def _data_json() -> str:
    """The flat unit list for the in-page calculator, from the same dicts as the
    table. `</` is escaped so no value can close the <script> it sits in."""
    data = {u["k"]: {"sqm": u["sqm"], "est": u["est"], "note": u["note"]}
            for u in _flat_units()}
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _sqm_of(key: str) -> float:
    return next(u["sqm"] for u in _flat_units() if u["k"] == key)


_CSS = """
.zm-head{text-align:center;margin:14px 0 12px}
.zm-head h1{margin:0;font-size:21px;line-height:1.3;color:var(--text-dark)}
.zm-calc{max-width:380px;margin:0 auto 12px;background:#1c3a2c;border-radius:26px;
padding:16px 14px 14px;box-shadow:0 10px 28px rgba(20,45,33,.28)}
.zm-screen{background:#dfe9d6;border-radius:16px;padding:4px 14px;
box-shadow:inset 0 2px 6px rgba(0,0,0,.18)}
.zm-line{padding:8px 0}
.zm-mid{display:flex;align-items:center;gap:10px}
.zm-mid::before,.zm-mid::after{content:"";flex:1;border-top:1px dashed rgba(28,58,44,.35)}
.zm-line select{font:inherit;font-size:14px;font-weight:700;color:#1c3a2c;
background-color:rgba(28,58,44,.1);border:0;border-radius:20px;padding:6px 28px 6px 12px;
max-width:100%;cursor:pointer;-webkit-appearance:none;appearance:none;
background-image:linear-gradient(45deg,transparent 50%,#1c3a2c 50%),linear-gradient(135deg,#1c3a2c 50%,transparent 50%);
background-position:calc(100% - 15px) 55%,calc(100% - 10px) 55%;background-size:5px 5px;background-repeat:no-repeat}
.zm-num{font-variant-numeric:tabular-nums;text-align:right;font-weight:700;color:#10241b;
font-size:38px;line-height:1.15;margin-top:6px;overflow-wrap:anywhere;min-height:44px}
.zm-line.to .zm-num{color:#2d6a4f}
.zm-swap{width:40px;height:40px;flex:none;
border-radius:50%;border:0;background:#e0a526;color:#1c3a2c;font-size:19px;
font-weight:800;cursor:pointer;line-height:1;padding:0}
.zm-keys{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-top:14px}
.zm-keys button{font:inherit;font-size:24px;font-weight:600;height:58px;border:0;border-radius:16px;
background:#2f5443;color:#fff;cursor:pointer;-webkit-tap-highlight-color:transparent;
font-variant-numeric:tabular-nums}
.zm-keys button:active{background:#44705b}
.zm-keys .fn{background:#dfe9d6;color:#1c3a2c;font-size:20px}
.zm-keys .fn:active{background:#c9d8bf}
.zm-keys .zero{grid-column:span 2}
.zm-hint{max-width:380px;margin:0 auto 20px;font-size:12.5px;color:var(--text-soft);
text-align:center;line-height:1.5}
.zm-hint:empty{display:none}
.zm-more{max-width:640px;margin:0 auto;border-top:1px solid var(--border)}
.zm-more summary{cursor:pointer;font-weight:700;padding:14px 2px;color:var(--text-dark)}
.zm-tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:4px 0 10px}
.zm-table{border-collapse:collapse;width:100%;font-size:14px;min-width:480px}
.zm-table th,.zm-table td{border-bottom:1px solid var(--border);padding:9px 8px;text-align:left}
.zm-table th{font-size:12.5px;color:var(--text-soft)}
"""

# The calculator. Runs entirely in the page; nothing is sent or stored.
_JS = """
(function(){
var U=JSON.parse(document.getElementById('zm-data').textContent),
    from=document.getElementById('zm-from'),to=document.getElementById('zm-to'),
    a=document.getElementById('zm-a'),b=document.getElementById('zm-b'),
    hint=document.getElementById('zm-hint'),s='1';
function grp(t){var p=t.split('.'),i=Number(p[0]||0).toLocaleString('en-IN');
  return p.length>1?i+'.'+p[1]:i;}
function fmt(x){
  if(!isFinite(x))return '0';
  if(x>=100)return x.toLocaleString('en-IN',{maximumFractionDigits:2});
  if(x>=1)return x.toLocaleString('en-IN',{maximumFractionDigits:3});
  return x.toLocaleString('en-IN',{maximumSignificantDigits:4});
}
function show(){
  var f=U[from.value],t=U[to.value];
  a.textContent=s===''?'0':grp(s);
  b.textContent=fmt((parseFloat(s)||0)*f.sqm/t.sqm);
  var e=f.est?f:(t.est?t:null);
  hint.textContent=e?'* बीघा-बिस्वा-कट्ठा का नाप अनुमानित है, ज़िले के हिसाब से बदल सकता है। '+
    (e.note?e.note+' ':'')+'रजिस्ट्री के लिए लेखपाल/पटवारी से पक्का नाप पूछें।':'';
}
function press(k){
  if(k==='C')s='';
  else if(k==='back')s=s.slice(0,-1);
  else if(k==='swap'){var x=from.value;from.value=to.value;to.value=x;}
  else if(k==='.'){if(s.indexOf('.')<0)s=(s||'0')+'.';}
  else if((s+k).replace('.','').length<=10)s=(s==='0'?'':s)+k;
  show();
}
document.querySelectorAll('[data-k]').forEach(function(el){
  el.addEventListener('click',function(){press(el.getAttribute('data-k'));});});
document.addEventListener('keydown',function(e){
  var t=e.target.tagName;
  if(t==='SELECT'||t==='INPUT'||t==='TEXTAREA'||e.ctrlKey||e.metaKey||e.altKey)return;
  var k=e.key;
  if(/^[0-9.]$/.test(k))press(k);
  else if(k==='Backspace')press('back');
  else if(k==='Escape'||k==='Delete')press('C');
  else return;
  e.preventDefault();
});
from.addEventListener('change',show);to.addEventListener('change',show);
show();
})();
"""


@router.get("/bigha-calculator", response_class=HTMLResponse)
def bigha_calculator():
    up = STATES["up"]["local"][0][3] * SQFT
    wb = STATES["west-bengal"]["local"][0][3] * SQFT
    first = _num(_sqm_of(DEFAULT_FROM) / _sqm_of(DEFAULT_TO))

    faqs = [
        ("1 बीघा में कितने एकड़ होते हैं?",
         f"यह राज्य पर निर्भर है। उत्तर प्रदेश के पक्के बीघे में लगभग {_num(up / ACRE)} एकड़ "
         f"(1 एकड़ = {_num(ACRE / up)} बीघा) होता है, जबकि पश्चिम बंगाल और असम के बीघे में "
         f"लगभग {_num(wb / ACRE)} एकड़। ऊपर इकाई में अपने राज्य का बीघा चुनकर सही हिसाब देखें।"),
        ("1 हेक्टेयर में कितने एकड़ होते हैं?",
         f"1 हेक्टेयर = {_num(10000 / ACRE)} एकड़ = 10,000 वर्ग मीटर। यह हर राज्य में एक ही है।"),
        ("1 बीघा में कितने बिस्वा या कट्ठा होते हैं?",
         "उत्तर प्रदेश, बिहार, बंगाल और राजस्थान में 1 बीघा = 20 बिस्वा (बिहार-बंगाल में कट्ठा)। "
         "असम में 1 बीघा = 5 कठा होता है।"),
        ("क्या यहाँ दिया बीघा सरकारी नाप है?",
         "नहीं। कृषि मित्र एक निजी वेबसाइट है। बीघा का यहाँ दिया नाप उस राज्य में आम तौर पर "
         "माना जाने वाला अनुमान है; एक ही राज्य के अलग-अलग ज़िलों में बीघा अलग हो सकता है। "
         "रजिस्ट्री, खतौनी या बँटवारे के लिए अपने लेखपाल, पटवारी या तहसील से पक्का नाप पूछें।"),
    ]
    faq_html, faq_ld = _faq(faqs)
    crumb_ld = _crumb_ld([("कृषि मित्र", f"{SITE}/"),
                          ("खेत नापें", f"{SITE}/naksha"),
                          ("बीघा कैलकुलेटर", CANON)])
    ld = _ld(faq_ld, crumb_ld)

    # (data-k, face, class, spoken label) — 4 columns. ⇅ lives on the screen, between the two rows.
    keys = "".join(
        f'<button type="button" data-k="{k}"{c} aria-label="{lbl}">{t}</button>'
        for k, t, c, lbl in [
            ("7", "7", "", "7"), ("8", "8", "", "8"), ("9", "9", "", "9"),
            ("back", "⌫", ' class="fn"', "मिटाएँ"),
            ("4", "4", "", "4"), ("5", "5", "", "5"), ("6", "6", "", "6"),
            ("C", "C", ' class="fn"', "सब साफ़ करें"),
            ("1", "1", "", "1"), ("2", "2", "", "2"), ("3", "3", "", "3"),
            (".", ".", ' class="fn"', "दशमलव"),
            ("0", "0", ' class="zero"', "0"), ("00", "00", ' class="zero"', "00"),
        ])

    body = f"""<div class="zm-head"><h1>बीघा ↔ एकड़ कैलकुलेटर</h1></div>

<section class="zm-calc" aria-label="ज़मीन इकाई कैलकुलेटर">
<div class="zm-screen">
<div class="zm-line from">
<select id="zm-from" aria-label="किस इकाई से">{_options(DEFAULT_FROM)}</select>
<div class="zm-num" id="zm-a">1</div>
</div>
<div class="zm-mid"><button type="button" class="zm-swap" data-k="swap" aria-label="इकाई अदला-बदली करें">⇅</button></div>
<div class="zm-line to">
<select id="zm-to" aria-label="किस इकाई में">{_options(DEFAULT_TO)}</select>
<div class="zm-num" id="zm-b" aria-live="polite">{first}</div>
</div>
</div>
<div class="zm-keys">{keys}</div>
</section>
<p class="zm-hint" id="zm-hint"></p>

<details class="zm-more">
<summary>किस राज्य में 1 बीघा कितना होता है?</summary>
{_state_table()}
</details>
<details class="zm-more">
<summary>अक्सर पूछे जाने वाले सवाल</summary>
{faq_html}
</details>
<script type="application/json" id="zm-data">{_data_json()}</script>
<script>{_JS}</script>"""

    crumbs = (f'<a href="{SITE}/">कृषि मित्र</a> › '
              f'<a href="{SITE}/naksha">खेत नापें</a> › बीघा कैलकुलेटर')
    desc = ("1 बीघा में कितने एकड़? अपने राज्य का बीघा, बिस्वा, कट्ठा, गुंठा, कनाल चुनकर "
            "एकड़, हेक्टेयर और वर्ग फुट में बदलें — यूपी, बिहार, बंगाल, राजस्थान समेत। मुफ़्त।")
    return _doc("बीघा से एकड़ कैलकुलेटर — राज्यवार बीघा, बिस्वा, कट्ठा, हेक्टेयर",
                desc, CANON, crumbs, body, ld, active="", extra_css=_CSS)


