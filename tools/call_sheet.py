# ============================================================
# KrashiMitra — the dealer call sheet
#
# The 31 Aug test (docs/MARKET-AND-MONEY.md §8) costs about ten phone calls,
# and on 20 Aug 2026 the `buyers` table held zero rows: not zero paid, zero
# *called*. §8.4 is explicit that "the calls never happened" is not a signal
# about the market, so a deadline that arrives with an empty call log produces
# no information at all. This exists to remove every step between deciding to
# call and dialling.
#
# It ranks districts by the only honest number we have. The stronger pitch the
# kharidar page was designed around — _sell_intent()'s "इस जिले में 14 किसानों
# ने बेचने के लिए कहा है" — needs crop_appeals rows, and there are none, so
# quoting it would be inventing demand. Search impressions are real, they are
# per-district, and they are already earned.
#
#   python tools/call_sheet.py              # top 12 districts
#   python tools/call_sheet.py --top 25
#
# Regenerate it rather than editing the output: the numbers move every week,
# and a call sheet quoting last month's impressions is a call sheet that gets
# a dealer's trust exactly once.
#
# TRACKING DOES NOT LIVE HERE. This file is the briefing; the record of who
# was rung goes on the dealer's own row via POST /admin/buyers/{slug}/call —
# one place, the same row that later carries the payment.
# ============================================================

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.routes import bhav  # noqa: E402
from backend.services import placements  # noqa: E402

GSC_DIR = ROOT / "scratch" / "gsc"
OUT = ROOT / "docs" / "CALL-SHEET.md"
SITE = "https://krashimitra.in"

# Slugs that sit in the district slot of the tier-4 tree but are not districts.
NOT_A_DISTRICT = {"kharidar", "msp"}


def latest_pages_file():
    files = sorted(GSC_DIR.glob("pages_*.json"))
    if not files:
        raise SystemExit(
            "no GSC rows in scratch/gsc — run: "
            "python tools/gsc_report.py --days 28 --page /bhav"
        )
    return files[-1]


def load(path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("pages") or []
    return rows


def by_district(rows):
    """Fold page rows into (state, district) -> impressions, clicks, crop mix."""
    out = collections.defaultdict(
        lambda: {"impr": 0, "clicks": 0, "crops": collections.Counter()}
    )
    for r in rows:
        url = r.get("keys", [r.get("page", "")])[0]
        m = re.search(r"/bhav/([^/]+)/([^/?#]+)/([^/?#]+)", url)
        if not m:
            continue
        crop, state, district = m.groups()
        if district in NOT_A_DISTRICT:
            continue
        d = out[(state, district)]
        d["impr"] += r.get("impressions", 0)
        d["clicks"] += r.get("clicks", 0)
        d["crops"][crop] += r.get("impressions", 0)
    return out


def hi(slug):
    """Fallback display name for a slug we cannot resolve to a real name."""
    return slug.replace("-", " ").title()


def crop_name(idx, slug):
    """The Hindi crop name, because this sheet is read out loud on a phone.

    "Sehore के Garlic भाव" is not a sentence anyone says; "सीहोर के लहसुन भाव"
    is. Resolved through the same slug index and the same _hindi_name() the
    /bhav page itself uses, so the sheet and the page can never call a crop by
    two different names — the dealer is going to open that page while you talk.

    _title_names returns (hi, en, same); when `same` is True there is no real
    translation for this commodity, and the English short name is all there is.
    """
    commodity = (idx.get("crops") or {}).get(slug)
    if not commodity:
        return hi(slug)
    name_hi, name_en, same = bhav._title_names(commodity)
    return name_en if same else name_hi


def district_name(idx, s_slug, d_slug):
    """The district as Agmarknet spells it — English, and left that way.

    There is no Hindi district map in the repo, and inventing transliterations
    for 514 districts is how a call sheet ends up naming a place something the
    person who lives there does not recognise.
    """
    try:
        return bhav._dist_name(idx, s_slug, d_slug) or hi(d_slug)
    except Exception:
        return hi(d_slug)


def build(top, dist, period, q1, q3, idx):
    L = []
    w = L.append

    w("# डीलर कॉल शीट — 31 अगस्त का टेस्ट")
    w("")
    w(f"*`tools/call_sheet.py` से बना, GSC {period} के डेटा पर। "
      "हाथ से मत बदलिए — दोबारा जनरेट कीजिए (उस फाइल का हेडर देखें)।*")
    w("")

    w("## एक लाइन में")
    w("")
    w("दस फ़ोन कॉल। बस यही बचा है। कोड में कुछ नहीं अटका — प्रॉस्पेक्ट जोड़ने से "
      "लेकर पैसा दर्ज करने तक सब बना हुआ है (नीचे *The admin loop*)।")
    w("")

    w("## क्या बेचना है")
    w("")
    w("`/bhav/{फसल}/{राज्य}/{ज़िला}/kharidar` — भाव देखने वाले किसान को यह पेज "
      "बताता है कि **इस ज़िले में खरीदार कौन है**। डीलर का नाम, दुकान और "
      "WhatsApp बटन उसी पेज पर।")
    w("")
    w(f"- **₹{q1}** — एक ज़िला, एक सीज़न ({placements.SEASON_MONTHS} महीने)")
    w("- **+₹50** — हर फसल पेज")
    w(f"- यानी एक ज़िला + 3 फसल = **₹{q3} / सीज़न** "
      f"(लगभग ₹{round(q3 / placements.SEASON_MONTHS)} महीना)")
    w("")
    w("दाम जान-बूझकर कम है। टेस्ट यह नहीं है कि कितना मिला — टेस्ट यह है कि "
      "**कोई देता भी है या नहीं**। ₹199 वह दाम है जिस पर दुकानदार सोचता नहीं, "
      "हाँ कह देता है।")
    w("")

    w("## किसे कॉल करना है")
    w("")
    w("ऊपर से नीचे। हर लाइन में जो नंबर है, वही फ़ोन पर बोलना है।")
    w("")
    w("| # | ज़िला | पिछले 28 दिन | सबसे बड़ी फसल | WhatsApp पर यह लिंक भेजें |")
    w("|---|---|---|---|---|")
    for i, ((state, d), v) in enumerate(top, 1):
        crop, cimpr = v["crops"].most_common(1)[0]
        w(f"| {i} | **{district_name(idx, state, d)}**, "
          f"{bhav._hindi_state(bhav._state_name(idx, state)) or hi(state)} | "
          f"**{v['impr']:,}** बार देखा ({v['clicks']} क्लिक) | "
          f"**{crop_name(idx, crop)}** — {cimpr:,} | "
          f"`{SITE}/bhav/{crop}/{state}/{d}` |")
    w("")
    tot = sum(v["impr"] for v in dist.values())
    w(f"*{len(dist)} ज़िलों में कुछ न कुछ ट्रैफ़िक है; ज़िला-पेजों पर कुल "
      f"{tot:,} impressions / 28 दिन।*")
    w("")

    w("## फ़ोन पर क्या बोलना है")
    w("")
    if top:
        (st0, d0), v0 = top[0]
        crop0, c0 = v0["crops"].most_common(1)[0]
        d0_name, crop0_name = district_name(idx, st0, d0), crop_name(idx, crop0)
        w(f"पहली कॉल {d0_name} के {crop0_name} व्यापारी को — "
          "सबसे मज़बूत नंबर वहीं है।")
        w("")
        w("> नमस्ते, मैं **कृषि मित्र** (krashimitra.in) से बोल रहा हूँ। "
          "हम मंडी भाव की वेबसाइट चलाते हैं।")
        w(">")
        w(f"> पिछले महीने अकेले **{d0_name} के {crop0_name} भाव** वाले पेज को "
          f"गूगल पर **{c0:,} बार** किसानों ने देखा।")
        w(">")
        w("> उस पेज पर एक हिस्सा है — *खरीदार कौन है* — वह अभी खाली है। भाव देखकर "
          "किसान का अगला सवाल यही होता है: अब बेचूँ किसे।")
        w(">")
        w(f"> **₹{q1} में तीन महीने** आपकी दुकान का नाम और WhatsApp नंबर वहाँ लगेगा। "
          "किसान सीधे आपको मैसेज करेगा — बीच में हम नहीं।")
        w("")

    w("### जो सवाल आएंगे")
    w("")
    w("**“कितने किसान कॉल करेंगे?”** — यही वह जगह है जहाँ झूठ नहीं बोलना। "
      "*“गारंटी नहीं दे सकता। पेज कितनी बार देखा गया, वह नंबर मैंने आपको बता "
      "दिया — उसमें से कितने फ़ोन करेंगे यह मुझे नहीं पता। इसीलिए दाम ₹199 है, "
      "₹5,000 नहीं। तीन महीने बाद आप खुद तय कर लेना।”*")
    w("")
    w("**“फ्री में लगा दो, चला तो पैसे दूँगा”** — यहीं टेस्ट फेल होता है। मुफ़्त "
      "लिस्टिंग सवाल का जवाब नहीं देती। *“₹199 पूरे तीन महीने का है — महीने का "
      "₹66। इतने में एक बार का डीज़ल भी नहीं आता।”*")
    w("")
    w("**“आप कौन हो, भरोसा कैसे करूँ?”** — लिंक भेज दीजिए। पेज असली है, गूगल पर "
      "आता है, और वह अपने ही ज़िले का भाव उसमें देख सकता है।")
    w("")
    w("**“सोचकर बताता हूँ”** — *“ठीक है, लिंक WhatsApp कर देता हूँ।”* — और उसी "
      "वक़्त admin में उसकी row बना दीजिए, वरना वह याद नहीं रहेगा।")
    w("")

    w("## नंबर कहाँ से मिलेंगे")
    w("")
    w("इनमें से कोई लिस्ट हमारे पास तैयार नहीं है — ये ढूँढने की जगहें हैं:")
    w("")
    w("- **Google Maps** — `कृषि सेवा केंद्र <ज़िला>` / `krishi seva kendra "
      "<district>`। नंबर सीधे लिस्टिंग पर। सबसे तेज़ रास्ता।")
    w("- **मंडी समिति (APMC)** — हर मंडी के पास लाइसेंसी व्यापारियों की सूची होती "
      "है। एक फ़ोन मंडी ऑफिस को।")
    w("- **IndiaMART / Justdial** — `<ज़िला> grain merchant`, `fertilizer dealer`।")
    w("- **खुद मंडी जाकर** — ऊपर की लिस्ट का ज़िला पास हो तो एक चक्कर दस कॉल पर भारी है।")
    w("")

    w("## The admin loop")
    w("")
    w("हर कॉल का हिसाब डीलर की अपनी row पर — अलग शीट कभी नहीं:")
    w("")
    w("| कब | क्या | कहाँ |")
    w("|---|---|---|")
    w("| कॉल से पहले | प्रॉस्पेक्ट की row बनाएँ (`active:false` ही रहेगी) | "
      "`POST /admin/buyers` |")
    w("| कॉल के तुरंत बाद | नतीजा दर्ज करें — `interested` / `pitched` / "
      "`not_interested` | `POST /admin/buyers/{slug}/call` |")
    w("| हाँ बोले तो | UPI कलेक्ट मोडल से पैसा माँगें | "
      "`GET /admin/buyers/{slug}/collect` |")
    w("| बैंक में पैसा दिखे तब | हाथ से दर्ज करें — कोई ऑटो-कन्फर्म नहीं | "
      "`POST /admin/buyers/{slug}/payment` |")
    w("| फ़ोन पर बात करके | तभी लाइव करें | admin approve |")
    w("")
    w("पैसा आने से डीलर लाइव नहीं होता — `record_payment()` जान-बूझकर "
      "`active`/`verified` को हाथ नहीं लगाता। बात हुए बिना ब्लू टिक नहीं, "
      "क्योंकि वह टिक ही पूरा प्रोडक्ट है।")
    w("")

    w("## 31 अगस्त को क्या लिखना है")
    w("")
    w("§8.4 दो नतीजों में फ़र्क करता है, और वे उल्टी दिशाओं में ले जाते हैं:")
    w("")
    w("- **“पूछा, उन्होंने मना किया”** → असली सिग्नल। बाज़ार पैसे नहीं देगा।")
    w("- **“कॉल हुई ही नहीं”** → बाज़ार के बारे में कोई सिग्नल नहीं। टेस्ट दोबारा चलाइए।")
    w("")
    w("आज तक `called_at` शून्य rows पर सेट है। जब तक पहली कॉल नहीं होती, "
      "31 अगस्त सिर्फ़ दूसरी लाइन दोहराएगा।")
    w("")

    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    src = latest_pages_file()
    period = src.stem.replace("pages_", "").replace("_", " → ")
    dist = by_district(load(src))
    top = sorted(dist.items(), key=lambda kv: -kv[1]["impr"])[: args.top]

    idx = bhav._get_index()
    text = build(top, dist, period,
                 placements.quote(1, 0), placements.quote(1, 3), idx)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(top)} districts, source {src.name})")


if __name__ == "__main__":
    raise SystemExit(main())
