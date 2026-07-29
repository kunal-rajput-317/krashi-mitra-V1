# Builds the two things the नक्शा pages are rendered from:
#
#   backend/data/naksha_states.json   — one record per state/UT: names, district
#                                       list, the numbers the pages quote, image
#                                       dimensions. backend/routes/naksha.py
#                                       serves /naksha, /naksha/<state> and
#                                       /naksha/<state>/jile straight off this.
#   frontend/map-download.js          — KM_STATE_MAPS, the download picker's and
#                                       the map switcher's copy of the same list.
#
#   python make_naksha_data.py
#
# Run it after make_state_maps.py. There are no per-state HTML files any more:
# 36 states × 2 page types = 72 built files was a copy of /bhav's problem, and
# /bhav's answer — one route, one template, data on disk — is the answer here
# too. Every number a page states (district count, image size, download
# filename, north-to-south span, biggest/smallest district) is read back off the
# generated geojson and PNG, never typed.

import json
import math
from pathlib import Path

from make_state_maps import STATES, outer_rings, shoelace

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
MANIFEST = ROOT / "backend" / "data" / "naksha_states.json"
PICKER = FRONTEND / "map-download.js"

# Where a farmer looks for their state on the hub. Geographic, not
# administrative: "उत्तर भारत" is how someone scans a list of 36, "केंद्र शासित
# प्रदेश" is not.
REGIONS = {
    "उत्तर भारत": ["uttar-pradesh", "rajasthan", "punjab", "haryana", "delhi",
                   "himachal-pradesh", "uttarakhand", "jammu-and-kashmir",
                   "ladakh", "chandigarh"],
    "मध्य भारत": ["madhya-pradesh", "chhattisgarh"],
    "पूर्वी भारत": ["bihar", "jharkhand", "west-bengal", "odisha"],
    "पश्चिमी भारत": ["gujarat", "maharashtra", "goa", "dnh-and-dd"],
    "दक्षिण भारत": ["karnataka", "telangana", "andhra-pradesh", "tamil-nadu",
                    "kerala", "puducherry", "lakshadweep",
                    "andaman-and-nicobar-islands"],
    "पूर्वोत्तर भारत": ["assam", "arunachal-pradesh", "manipur", "meghalaya",
                        "mizoram", "nagaland", "sikkim", "tripura"],
}


def districts(cfg) -> list:
    """Every district in the state's own generated geojson, with the centroid
    latitude and the area used to rank them.

    Area is in square degrees corrected for longitude convergence — enough to
    rank districts within one state, which is all it is for. No km² figure is
    ever published: the polygons are simplified, and a wrong-looking number is
    worse than no number.
    """
    data = json.loads((FRONTEND / "data" / cfg["geojson"]).read_text(encoding="utf-8"))
    out = []
    for f in data["features"]:
        rings = list(outer_rings(f["geometry"]))
        # Biggest ring decides where a district "is" — an island or an exclave
        # must not drag the centroid out to sea.
        _, _, cy = max((shoelace(r) for r in rings), key=lambda t: t[0])
        out.append({"hi": f["properties"]["district_hi"],
                    "en": f["properties"]["district"],
                    "lat": cy,
                    "area": sum(shoelace(r)[0] for r in rings) * math.cos(math.radians(cy))})
    return out


def png_size(cfg) -> tuple:
    from PIL import Image
    with Image.open(FRONTEND / "images" / f"{cfg['prefix']}-district-map.png") as im:
        return im.size


def region_of(key: str) -> str:
    for name, keys in REGIONS.items():
        if key in keys:
            return name
    raise SystemExit(f"{key!r} is in STATES but in no region — add it to REGIONS")


def record(key: str, cfg: dict) -> dict:
    ds = districts(cfg)
    w, h = png_size(cfg)
    ordered = sorted(ds, key=lambda d: d["hi"])
    return {
        "key": key,
        "hi": cfg["hi"], "en": cfg["en"], "kn": cfg["kn"],
        "iso": cfg["iso"],
        "lat": cfg["center"][0], "lon": cfg["center"][1],
        "region": region_of(key),
        "prefix": cfg["prefix"],
        "geojson": cfg["geojson"],
        "note": cfg.get("note", ""),
        "n": len(ds),
        "north": max(ds, key=lambda d: d["lat"])["hi"],
        "south": min(ds, key=lambda d: d["lat"])["hi"],
        "big": max(ds, key=lambda d: d["area"])["hi"],
        "small": min(ds, key=lambda d: d["area"])["hi"],
        "w": w, "h": h,
        "districts": [{"hi": d["hi"], "en": d["en"]} for d in ordered],
    }


def sync_picker(records: dict) -> bool:
    """Rewrite `var STATES = {…}` in map-download.js from the same records.

    The picker prints a district count and names the file it hands over, so both
    have to be the numbers baked into the images — hand-typing them here is how
    a picker ends up offering "33 जिले" for a 52-district map. Keys are quoted:
    `madhya-pradesh` is not a bare JS identifier and an unquoted one takes the
    whole file down with a syntax error.
    """
    rows = []
    for key, r in records.items():
        rows.append(f"""    '{key}': {{
      hi: '{r["hi"]}', en: '{r["en"]}', kn: '{r["kn"]}',
      districts: {r["n"]}, region: '{r["region"]}',
      png:  abs('images/{r["prefix"]}-district-map.png'),
      file: '{r["prefix"]}-{r["n"]}-jile.png',
      page: '{"/map" if key == "uttar-pradesh" else f"/naksha/{key}"}'
    }}""")
    head = "  // GENERATED by make_naksha_data.py"
    block = [f"{head} — edit STATES in make_state_maps.py instead.",
             "  var STATES = {"] + ",\n".join(rows).split("\n") + ["  };"]

    src = PICKER.read_text(encoding="utf-8")
    lines = src.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("  var STATES = {"))
    while start and lines[start - 1].startswith("  // GENERATED by make_naksha"):
        start -= 1
    end = next(i for i in range(start, len(lines)) if lines[i] == "  };")
    new = "\n".join(lines[:start] + block + lines[end + 1:])
    if new == src:
        return False
    PICKER.write_text(new, encoding="utf-8")
    return True


def main():
    records = {k: record(k, c) for k, c in STATES.items()}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"states": records}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    total = sum(r["n"] for r in records.values())
    print(f"manifest: {MANIFEST} — {len(records)} states/UTs, {total} districts")
    print("map-download.js:", "updated" if sync_picker(records) else "unchanged")


if __name__ == "__main__":
    main()
