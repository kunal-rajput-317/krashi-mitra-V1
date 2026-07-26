# One-time generator for the /map static assets, per state:
#   frontend/data/<slug>-districts.geojson          (minified, self-hosted boundaries)
#   frontend/images/<prefix>-district-map.png       (full labeled map, page + download)
#   frontend/images/<prefix>-district-map.webp      (light display copy)
#   frontend/images/<prefix>-og.png                 (1200x630 social/og card)
# Boundaries: udit-001/india-maps-data (Census of India). Needs playwright+chromium.
# Re-run only if district boundaries change or the map design is redone.
#
#   python make_state_maps.py                 # every state below
#   python make_state_maps.py rajasthan       # just one

import base64, json, math, os, sys, tempfile, urllib.request
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_URL = ("https://raw.githubusercontent.com/udit-001/india-maps-data/"
           "main/geojson/states/{source}.geojson")
OUT_DIR = ROOT / "frontend" / "data"
IMG_DIR = ROOT / "frontend" / "images"
LOGO    = ROOT / "frontend" / "assets" / "krashimitra_logo.png"

UP_HINDI = {
 "Agra":"आगरा","Aligarh":"अलीगढ़","Ambedkar Nagar":"अंबेडकर नगर","Amethi":"अमेठी",
 "Amroha":"अमरोहा","Auraiya":"औरैया","Ayodhya":"अयोध्या","Azamgarh":"आज़मगढ़",
 "Baghpat":"बागपत","Bahraich":"बहराइच","Ballia":"बलिया","Balrampur":"बलरामपुर",
 "Banda":"बांदा","Barabanki":"बाराबंकी","Bareilly":"बरेली","Basti":"बस्ती",
 "Bhadohi":"भदोही","Bijnor":"बिजनौर","Budaun":"बदायूं","Bulandshahr":"बुलंदशहर",
 "Chandauli":"चंदौली","Chitrakoot":"चित्रकूट","Deoria":"देवरिया","Etah":"एटा",
 "Etawah":"इटावा","Farrukhabad":"फर्रुखाबाद","Fatehpur":"फतेहपुर","Firozabad":"फिरोज़ाबाद",
 "Gautam Buddha Nagar":"गौतम बुद्ध नगर","Ghaziabad":"गाज़ियाबाद","Ghazipur":"गाज़ीपुर",
 "Gonda":"गोंडा","Gorakhpur":"गोरखपुर","Hamirpur":"हमीरपुर","Hapur":"हापुड़",
 "Hardoi":"हरदोई","Hathras":"हाथरस","Jalaun":"जालौन","Jaunpur":"जौनपुर",
 "Jhansi":"झांसी","Kannauj":"कन्नौज","Kanpur Dehat":"कानपुर देहात","Kanpur Nagar":"कानपुर नगर",
 "Kasganj":"कासगंज","Kaushambi":"कौशांबी","Kushinagar":"कुशीनगर","Lakhimpur Kheri":"लखीमपुर खीरी",
 "Lalitpur":"ललितपुर","Lucknow":"लखनऊ","Maharajganj":"महाराजगंज","Mahoba":"महोबा",
 "Mainpuri":"मैनपुरी","Mathura":"मथुरा","Mau":"मऊ","Meerut":"मेरठ",
 "Mirzapur":"मिर्ज़ापुर","Moradabad":"मुरादाबाद","Muzaffarnagar":"मुज़फ्फरनगर","Pilibhit":"पीलीभीत",
 "Pratapgarh":"प्रतापगढ़","Prayagraj":"प्रयागराज","Rae Bareli":"रायबरेली","Rampur":"रामपुर",
 "Saharanpur":"सहारनपुर","Sambhal":"संभल","Sant Kabir Nagar":"संत कबीर नगर","Shahjahanpur":"शाहजहांपुर",
 "Shamli":"शामली","Shrawasti":"श्रावस्ती","Siddharthnagar":"सिद्धार्थनगर","Sitapur":"सीतापुर",
 "Sonbhadra":"सोनभद्र","Sultanpur":"सुल्तानपुर","Unnao":"उन्नाव","Varanasi":"वाराणसी",
}

# Census district set — predates Rajasthan's 2023 reorganisation, so the newer
# Beawar / Deeg / Didwana-Kuchaman etc. are not separate polygons here.
RAJ_HINDI = {
 "Ajmer":"अजमेर","Alwar":"अलवर","Banswara":"बांसवाड़ा","Baran":"बारां",
 "Barmer":"बाड़मेर","Bharatpur":"भरतपुर","Bhilwara":"भीलवाड़ा","Bikaner":"बीकानेर",
 "Bundi":"बूंदी","Chittorgarh":"चित्तौड़गढ़","Churu":"चूरू","Dausa":"दौसा",
 "Dholpur":"धौलपुर","Dungarpur":"डूंगरपुर","Ganganagar":"श्रीगंगानगर","Hanumangarh":"हनुमानगढ़",
 "Jaipur":"जयपुर","Jaisalmer":"जैसलमेर","Jalore":"जालोर","Jhalawar":"झालावाड़",
 "Jhunjhunu":"झुंझुनूं","Jodhpur":"जोधपुर","Karauli":"करौली","Kota":"कोटा",
 "Nagaur":"नागौर","Pali":"पाली","Pratapgarh":"प्रतापगढ़","Rajsamand":"राजसमंद",
 "Sawai Madhopur":"सवाई माधोपुर","Sikar":"सीकर","Sirohi":"सिरोही","Tonk":"टोंक",
 "Udaipur":"उदयपुर",
}

STATES = {
    "uttar-pradesh": {
        "source":  "uttar-pradesh",
        "geojson": "up-districts.geojson",
        "prefix":  "up-ka-naksha",
        "hi":      "उत्तर प्रदेश",
        "og_h1":   "उत्तर प्रदेश<br>का नक्शा",
        "hindi":   UP_HINDI,
    },
    "rajasthan": {
        "source":  "rajasthan",
        "geojson": "rajasthan-districts.geojson",
        "prefix":  "rajasthan-ka-naksha",
        "hi":      "राजस्थान",
        "og_h1":   "राजस्थान<br>का नक्शा",
        "hindi":   RAJ_HINDI,
    },
}

GREEN_DARK, GREEN_MID, GREEN_LIGHT, GREEN_PALE, AMBER = "#1a3c2e", "#2d6a4f", "#52b788", "#d8f3dc", "#e9a825"


def load_and_minify(cfg, scratch):
    raw = scratch / f"{cfg['source']}-raw.geojson"
    if not raw.exists():
        urllib.request.urlretrieve(RAW_URL.format(source=cfg["source"]), raw)
    g = json.load(open(raw, encoding="utf-8"))
    hindi = cfg["hindi"]
    feats = []
    for f in g["features"]:
        name = f["properties"]["district"]
        assert name in hindi, f"no Hindi name for {name}"
        geom = f["geometry"]

        def rnd(ring):
            out, prev = [], None
            for x, y in ring:
                p = [round(x, 4), round(y, 4)]
                if p != prev:
                    out.append(p)
                prev = p
            return out

        if geom["type"] == "Polygon":
            coords = [rnd(r) for r in geom["coordinates"]]
        else:
            coords = [[rnd(r) for r in poly] for poly in geom["coordinates"]]
        feats.append({"type": "Feature",
                      "properties": {"district": name, "district_hi": hindi[name]},
                      "geometry": {"type": geom["type"], "coordinates": coords}})
    out = {"type": "FeatureCollection", "features": feats}
    out_geo = OUT_DIR / cfg["geojson"]
    out_geo.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_geo, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("geojson:", out_geo, os.path.getsize(out_geo), "bytes")
    return out


def rings_of(geom):
    if geom["type"] == "Polygon":
        yield from geom["coordinates"]
    else:
        for poly in geom["coordinates"]:
            yield from poly


def outer_rings(geom):
    if geom["type"] == "Polygon":
        yield geom["coordinates"][0]
    else:
        for poly in geom["coordinates"]:
            yield poly[0]


def shoelace(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-12:
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    a *= 0.5
    return abs(a), cx / (6 * a), cy / (6 * a)


def build_svg(data, map_w, label_scale=1.0, labels=True):
    lons = [x for f in data["features"] for r in rings_of(f["geometry"]) for x, _ in r]
    lats = [y for f in data["features"] for r in rings_of(f["geometry"]) for _, y in r]
    lo_x, hi_x, lo_y, hi_y = min(lons), max(lons), min(lats), max(lats)
    klat = math.cos(math.radians((lo_y + hi_y) / 2))
    scale = map_w / ((hi_x - lo_x) * klat)
    map_h = (hi_y - lo_y) * scale

    def px(lon, lat):
        return ((lon - lo_x) * klat * scale, (hi_y - lat) * scale)

    paths, lbls = [], []
    for f in data["features"]:
        d = []
        for ring in rings_of(f["geometry"]):
            pts = [px(x, y) for x, y in ring]
            d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
        paths.append(f'<path d="{"".join(d)}" fill="{GREEN_PALE}" stroke="{GREEN_MID}" stroke-width="1.1"/>')
        if not labels:
            continue
        best = max((shoelace(r) for r in outer_rings(f["geometry"])), key=lambda t: t[0])
        area, cx, cy = best
        x, y = px(cx, cy)
        name = f["properties"]["district_hi"]
        # px area of the district drives label size
        apx = area * (klat * scale) * scale
        size = max(10.5, min(14.5, 7 + math.sqrt(apx) / 22)) * label_scale
        est_w = len(name) * size * 0.62
        dist_w = math.sqrt(apx) * 1.15
        halo = 'stroke="#ffffff" stroke-width="3" paint-order="stroke" stroke-linejoin="round"'
        if est_w > dist_w and " " in name:
            words = name.split(" ")
            mid = len(words) // 2 + len(words) % 2
            l1, l2 = " ".join(words[:mid]), " ".join(words[mid:])
            lbls.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size:.1f}" {halo}>'
                        f'<tspan x="{x:.0f}" dy="-{size*0.15:.0f}">{l1}</tspan>'
                        f'<tspan x="{x:.0f}" dy="{size*1.1:.0f}">{l2}</tspan></text>')
        else:
            lbls.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size:.1f}" {halo}>{name}</text>')
    return "".join(paths), "".join(lbls), map_w, map_h


FONT = "'Nirmala UI','Noto Sans Devanagari','Mangal',sans-serif"


@lru_cache(maxsize=1)
def logo_uri():
    """The कृषि मित्र emblem as a data: URI.

    Inlined rather than linked: the page being screenshotted is written to a
    temp dir, so a relative path can't reach frontend/assets and Chromium
    won't reliably load a file:// subresource from outside that dir.
    """
    return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()


def brand_mark(px=78, on_dark=False, url=False):
    """The कृषि मित्र lockup — emblem + wordmark. Returns (css, html).

    Single source for every generated image: the full district map and the og
    card both render this, so a state added to STATES later is branded without
    anyone remembering to do it. Only the palette flips between the white map
    and the dark og card — the mark itself never diverges.
    """
    ring = "rgba(255,255,255,.20)" if on_dark else GREEN_PALE
    word = "#ffffff" if on_dark else GREEN_DARK
    css = f"""
      .mark{{display:flex;align-items:center;gap:16px;flex-shrink:0}}
      .mark img{{width:{px}px;height:{px}px;border-radius:50%;object-fit:cover;
                box-shadow:0 0 0 4px {ring}}}
      .mark .mt{{font-size:{px * .40:.0f}px;font-weight:700;color:{word};
                letter-spacing:.3px;line-height:1.1}}
      .mark .mu{{font-size:{px * .28:.0f}px;font-weight:700;color:{AMBER};margin-top:3px}}"""
    sub = '<div class="mu">krashimitra.in</div>' if url else ""
    html = (f'<div class="mark"><img src="{logo_uri()}" alt="">'
            f'<div><div class="mt">कृषि मित्र</div>{sub}</div></div>')
    return css, html


def render(html_path, png_path, w, h):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.goto(html_path.resolve().as_uri())
        page.wait_for_timeout(400)
        page.screenshot(path=str(png_path))
        b.close()
    print("png:", png_path, os.path.getsize(png_path), "bytes")


def build_state(key):
    cfg = STATES[key]
    scratch = Path(tempfile.mkdtemp(prefix=f"{key}_map_"))
    data = load_and_minify(cfg, scratch)
    n = len(data["features"])
    hi, prefix = cfg["hi"], cfg["prefix"]
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # ── full labeled map ──
    # The map is a free HD download that gets reshared off-site, so it travels
    # with the mark on it.
    mark_css, mark_html = brand_mark(px=78)
    paths, lbls, mw, mh = build_svg(data, map_w=1340)
    W, H = 1440, int(mh) + 190
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      *{{margin:0;padding:0}} body{{width:{W}px;height:{H}px;background:#fff;font-family:{FONT}}}
      .head{{padding:26px 50px 10px;display:flex;align-items:center;justify-content:space-between;gap:40px}}
      h1{{font-size:34px;color:{GREEN_DARK};font-weight:700}}
      h1 span{{color:{AMBER}}} .sub{{font-size:17px;color:{GREEN_MID};margin-top:4px}}
      .bar{{width:110px;height:5px;background:{AMBER};border-radius:3px;margin-top:10px}}{mark_css}
      svg text{{fill:{GREEN_DARK};font-family:{FONT};text-anchor:middle;font-weight:600}}
      .foot{{position:absolute;bottom:12px;left:50px;right:50px;display:flex;justify-content:space-between;
             font-size:13px;color:#7a8a80}} .foot b{{color:{GREEN_MID}}}
    </style></head><body>
      <div class="head">
        <div><h1>{hi} का नक्शा <span>— {n} जिले</span></h1>
        <div class="sub">जिलेवार मानचित्र • हर जिले का मंडी भाव व मौसम krashimitra.in पर</div><div class="bar"></div></div>
        {mark_html}
      </div>
      <div style="padding:6px 50px 0"><svg width="{mw:.0f}" height="{mh:.0f}" viewBox="0 0 {mw:.0f} {mh:.0f}">{paths}{lbls}</svg></div>
      <div class="foot"><span><b>krashimitra.in</b> — किसानों का साथी</span>
      <span>सीमा-डेटा: Census of India (india-maps-data)</span></div>
    </body></html>"""
    fp = scratch / f"{key}_map_full.html"
    fp.write_text(html, encoding="utf-8")
    render(fp, IMG_DIR / f"{prefix}-district-map.png", W, H)

    # ── og card 1200x630 ──
    # Same lockup, dark palette — it absorbs the old plain-text krashimitra.in line.
    og_mark_css, og_mark_html = brand_mark(px=76, on_dark=True, url=True)
    paths2, _, mw2, mh2 = build_svg(data, map_w=560, labels=False)
    html_og = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      *{{margin:0;padding:0}} body{{width:1200px;height:630px;background:{GREEN_DARK};font-family:{FONT};
        display:flex;align-items:center;overflow:hidden}}
      .l{{flex:1;padding:0 20px 0 64px}} h1{{font-size:58px;color:#fff;line-height:1.15;font-weight:700}}
      .sub{{font-size:26px;color:{GREEN_PALE};margin-top:18px}} .bar{{width:120px;height:6px;background:{AMBER};
        border-radius:3px;margin:26px 0}}{og_mark_css}
      .r{{width:600px;height:630px;display:flex;align-items:center;justify-content:center}}
      .r svg{{filter:drop-shadow(0 8px 24px rgba(0,0,0,.35))}}
    </style></head><body>
      <div class="l"><h1>{cfg["og_h1"]}</h1><div class="sub">{n} जिलों का जिलेवार मानचित्र</div>
      <div class="bar"></div>{og_mark_html}</div>
      <div class="r"><svg width="{mw2:.0f}" height="{mh2:.0f}" viewBox="0 0 {mw2:.0f} {mh2:.0f}"
        style="max-height:580px">{paths2.replace(GREEN_PALE, GREEN_LIGHT).replace(GREEN_MID, GREEN_DARK)}</svg></div>
    </body></html>"""
    fo = scratch / f"{key}_map_og.html"
    fo.write_text(html_og, encoding="utf-8")
    render(fo, IMG_DIR / f"{prefix}-og.png", 1200, 630)

    # ── light webp for in-page display ──
    from PIL import Image
    im = Image.open(IMG_DIR / f"{prefix}-district-map.png")
    im.save(IMG_DIR / f"{prefix}-district-map.webp", "WEBP", quality=82, method=6)
    print("webp:", os.path.getsize(IMG_DIR / f"{prefix}-district-map.webp"), "bytes")
    print(f"-> {key}: {n} districts, full map {W}x{H}\n")


def main():
    keys = sys.argv[1:] or list(STATES)
    for k in keys:
        if k not in STATES:
            raise SystemExit(f"unknown state {k!r}; known: {', '.join(STATES)}")
        build_state(k)


if __name__ == "__main__":
    main()
