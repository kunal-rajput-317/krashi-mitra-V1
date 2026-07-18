# One-time generator for the /map static assets:
#   frontend/data/up-districts.geojson       (minified, self-hosted boundaries)
#   frontend/images/up-ka-naksha-district-map.png   (full labeled map, page + download)
#   frontend/images/up-ka-naksha-district-map.webp  (light display copy)
#   frontend/images/up-ka-naksha-og.png             (1200x630 social/og card)
# Boundaries: udit-001/india-maps-data (Census of India). Needs playwright+chromium.
# Re-run only if district boundaries change or the map design is redone.

import json, math, os, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_URL = ("https://raw.githubusercontent.com/udit-001/india-maps-data/"
           "main/geojson/states/uttar-pradesh.geojson")
SCRATCH = Path(tempfile.mkdtemp(prefix="up_map_"))
RAW = SCRATCH / "up-districts-raw.geojson"
OUT_GEO = ROOT / "frontend" / "data" / "up-districts.geojson"
IMG_DIR = ROOT / "frontend" / "images"

HINDI = {
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

GREEN_DARK, GREEN_MID, GREEN_LIGHT, GREEN_PALE, AMBER = "#1a3c2e", "#2d6a4f", "#52b788", "#d8f3dc", "#e9a825"


def load_and_minify():
    if not RAW.exists():
        urllib.request.urlretrieve(RAW_URL, RAW)
    g = json.load(open(RAW, encoding="utf-8"))
    feats = []
    for f in g["features"]:
        name = f["properties"]["district"]
        assert name in HINDI, f"no Hindi name for {name}"
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
                      "properties": {"district": name, "district_hi": HINDI[name]},
                      "geometry": {"type": geom["type"], "coordinates": coords}})
    out = {"type": "FeatureCollection", "features": feats}
    OUT_GEO.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT_GEO, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("geojson:", OUT_GEO, os.path.getsize(OUT_GEO), "bytes")
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


def main():
    data = load_and_minify()
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # ── full labeled map ──
    paths, lbls, mw, mh = build_svg(data, map_w=1340)
    W, H = 1440, int(mh) + 190
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      *{{margin:0;padding:0}} body{{width:{W}px;height:{H}px;background:#fff;font-family:{FONT}}}
      .head{{padding:26px 50px 10px}} h1{{font-size:34px;color:{GREEN_DARK};font-weight:700}}
      h1 span{{color:{AMBER}}} .sub{{font-size:17px;color:{GREEN_MID};margin-top:4px}}
      .bar{{width:110px;height:5px;background:{AMBER};border-radius:3px;margin-top:10px}}
      svg text{{fill:{GREEN_DARK};font-family:{FONT};text-anchor:middle;font-weight:600}}
      .foot{{position:absolute;bottom:12px;left:50px;right:50px;display:flex;justify-content:space-between;
             font-size:13px;color:#7a8a80}} .foot b{{color:{GREEN_MID}}}
    </style></head><body>
      <div class="head"><h1>उत्तर प्रदेश का नक्शा <span>— 75 जिले</span></h1>
      <div class="sub">जिलेवार मानचित्र • हर जिले का मंडी भाव व मौसम krashimitra.in पर</div><div class="bar"></div></div>
      <div style="padding:6px 50px 0"><svg width="{mw:.0f}" height="{mh:.0f}" viewBox="0 0 {mw:.0f} {mh:.0f}">{paths}{lbls}</svg></div>
      <div class="foot"><span><b>krashimitra.in</b> — किसानों का साथी</span>
      <span>सीमा-डेटा: Census of India (india-maps-data)</span></div>
    </body></html>"""
    fp = SCRATCH / "up_map_full.html"
    fp.write_text(html, encoding="utf-8")
    render(fp, IMG_DIR / "up-ka-naksha-district-map.png", W, H)

    # ── og card 1200x630 ──
    paths2, _, mw2, mh2 = build_svg(data, map_w=560, labels=False)
    html_og = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      *{{margin:0;padding:0}} body{{width:1200px;height:630px;background:{GREEN_DARK};font-family:{FONT};
        display:flex;align-items:center;overflow:hidden}}
      .l{{flex:1;padding:0 20px 0 64px}} h1{{font-size:58px;color:#fff;line-height:1.15;font-weight:700}}
      .sub{{font-size:26px;color:{GREEN_PALE};margin-top:18px}} .bar{{width:120px;height:6px;background:{AMBER};
        border-radius:3px;margin:26px 0}} .brand{{font-size:30px;color:{AMBER};font-weight:700}}
      .r{{width:600px;height:630px;display:flex;align-items:center;justify-content:center}}
      .r svg{{filter:drop-shadow(0 8px 24px rgba(0,0,0,.35))}}
    </style></head><body>
      <div class="l"><h1>उत्तर प्रदेश<br>का नक्शा</h1><div class="sub">75 जिलों का जिलेवार मानचित्र</div>
      <div class="bar"></div><div class="brand">krashimitra.in</div></div>
      <div class="r"><svg width="{mw2:.0f}" height="{mh2:.0f}" viewBox="0 0 {mw2:.0f} {mh2:.0f}"
        style="max-height:580px">{paths2.replace(GREEN_PALE, GREEN_LIGHT).replace(GREEN_MID, GREEN_DARK)}</svg></div>
    </body></html>"""
    fo = SCRATCH / "up_map_og.html"
    fo.write_text(html_og, encoding="utf-8")
    render(fo, IMG_DIR / "up-ka-naksha-og.png", 1200, 630)

    # ── light webp for in-page display ──
    from PIL import Image
    im = Image.open(IMG_DIR / "up-ka-naksha-district-map.png")
    im.save(IMG_DIR / "up-ka-naksha-district-map.webp", "WEBP", quality=82, method=6)
    print("webp:", os.path.getsize(IMG_DIR / "up-ka-naksha-district-map.webp"), "bytes")


if __name__ == "__main__":
    main()
