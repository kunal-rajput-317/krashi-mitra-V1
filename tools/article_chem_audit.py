# -*- coding: utf-8 -*-
# ============================================================
# KrashiMitra — the agronomy verification worklist.
#
# The advisory block (tools/article_advisory.py) fixes the site's POSITION: the
# label is the authority, this page is general information. It does not make a
# wrong number right. 97 article pages carry a chemical name or a dose that was
# generated, not checked by an agronomist, and every one of those numbers still
# has to be read against an ICAR or state agri-university source.
#
# That is a weekend of work, so this tool decides the ORDER. It pulls every
# chemical and every dose out of the built pages with the sentence around it,
# and ranks the pages by the impressions they actually earn — because a wrong
# dose on a page with 42,000 impressions is not the same problem as the same
# wrong dose on a page with 3.
#
#   python tools/article_chem_audit.py          → docs/CHEM-AUDIT.md
#
# docs/ is gitignored; regenerate it, never hand-edit it. Tick items off in the
# source module (tools/articles/*.py) and rebuild, so a correction survives the
# next --all instead of being overwritten by it.
# ============================================================

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import article_advisory as adv          # noqa: E402
import article_builder as ab            # noqa: E402

GSC_DIR = ROOT / "scratch" / "gsc"
OUT = ROOT / "docs" / "CHEM-AUDIT.md"

# Molecules whose Indian registration status is contested or restricted, so a
# mention needs a status check and not only a dose check. This list is a
# PROMPT, never an authority: CIB&RC changes it, this file does not track it.
# Verify every one of these at cibrc.nic.in before acting on it.
WATCH = {
    "ग्लाइफोसेट": "glyphosate — restricted to Pest Control Operators (2022)",
    "glyphosate": "glyphosate — restricted to Pest Control Operators (2022)",
    "पैराक्वाट": "paraquat — banned in several states",
    "paraquat": "paraquat — banned in several states",
    "मोनोक्रोटोफॉस": "monocrotophos — banned on vegetables and fruit",
    "monocrotophos": "monocrotophos — banned on vegetables and fruit",
    "कार्बोफ्यूरान": "carbofuran — 50% SP banned",
    "carbofuran": "carbofuran — 50% SP banned",
    "कार्बेन्डाजिम": "carbendazim — 2020 draft-ban list",
    "कार्बेन्डाज़िम": "carbendazim — 2020 draft-ban list",
    "carbendazim": "carbendazim — 2020 draft-ban list",
    "क्विनालफॉस": "quinalphos — 2020 draft-ban list",
    "quinalphos": "quinalphos — 2020 draft-ban list",
    "डाइमेथोएट": "dimethoate — 2020 draft-ban list",
    "dimethoate": "dimethoate — 2020 draft-ban list",
    "मैलाथियान": "malathion — 2020 draft-ban list",
    "मेलाथियान": "malathion — 2020 draft-ban list",
    "malathion": "malathion — 2020 draft-ban list",
    "एट्राजीन": "atrazine — 2020 draft-ban list",
    "atrazine": "atrazine — 2020 draft-ban list",
    "थायरम": "thiram — 2020 draft-ban list",
    "thiram": "thiram — 2020 draft-ban list",
    "कैप्टान": "captan — 2020 draft-ban list",
    "captan": "captan — 2020 draft-ban list",
    "आइसोप्रोट्यूरॉन": "isoproturon — 2020 draft-ban list",
    "isoproturon": "isoproturon — 2020 draft-ban list",
    "डेल्टामेथ्रिन": "deltamethrin — 2020 draft-ban list",
    "deltamethrin": "deltamethrin — 2020 draft-ban list",
    "एसीफेट": "acephate — 2020 draft-ban list",
    "acephate": "acephate — 2020 draft-ban list",
    "क्लोरपायरीफॉस": "chlorpyriphos — crop-specific bans",
    "क्लोरपाइरीफॉस": "chlorpyriphos — crop-specific bans",
    "chlorpyriphos": "chlorpyriphos — crop-specific bans",
    "2,4-D": "2,4-D — state restrictions",
}


def _latest_gsc() -> tuple[dict[str, dict], str]:
    """{slug: {clicks, impressions}} from the best pages_*.json on disk.

    "Best" is the WIDEST window, not the newest file. Picking by mtime chose a
    3-day export sitting next to a 28-day one and ranked the whole worklist on
    7,404 impressions instead of 82,000 — which reorders which pages get
    checked first, the only thing this file decides.
    """
    files = sorted(GSC_DIR.glob("pages_*.json"))
    if not files:
        return {}, "no GSC data on disk"

    def span(p: Path):
        d = re.findall(r"(\d{4}-\d{2}-\d{2})", p.name)
        if len(d) == 2:
            from datetime import date
            a, b = (date.fromisoformat(x) for x in d)
            return ((b - a).days, b.isoformat())
        return (0, "")

    f = max(files, key=span)
    rows = json.loads(f.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for r in rows:
        page = r.get("page", "")
        m = re.search(r"/articles/([A-Za-z0-9_\-]+)", page)
        if m:
            out[m.group(1)] = r
    return out, f.name


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[।.!?])\s+", text) if s.strip()]


def audit() -> list[dict]:
    gsc, src = _latest_gsc()
    mods = {}
    for f in sorted(ab.CONTENT_DIR.glob("*.py")):
        if not f.name.startswith("_"):
            try:
                mods[ab._load_content(f)["slug"]] = f.name
            except Exception:
                pass

    rows = []
    for p in sorted(ab.ARTICLES.glob("*.html")):
        if p.stem == "index":
            continue
        doc = p.read_text(encoding="utf-8", errors="replace")
        own = re.split(r'<div class="relevant-articles">', doc)[0]
        own = re.sub(r'<div class="km-advisory".*?</div>', " ", own, flags=re.S)
        vis = ab._visible(own)
        chems, doses = adv.find_chemicals(vis), adv.find_doses(vis)
        if not (chems or doses):
            continue
        claims = []
        for s in _sentences(vis):
            c, d = adv.find_chemicals(s), adv.find_doses(s)
            if c and d:
                claims.append(s[:300])
        g = gsc.get(p.stem, {})
        rows.append({
            "slug": p.stem,
            "module": mods.get(p.stem, "— legacy, no content module —"),
            "impressions": int(g.get("impressions", 0)),
            "clicks": int(g.get("clicks", 0)),
            "chemicals": chems,
            "doses": doses,
            "claims": claims,
            "watch": sorted({v for c in chems for k, v in WATCH.items()
                             if k.lower() == c.lower()}),
        })
    rows.sort(key=lambda r: (-r["impressions"], -len(r["doses"])))
    return rows, src


def write(rows, src) -> str:
    tot_i = sum(r["impressions"] for r in rows)
    watch = [r for r in rows if r["watch"]]
    run = 0
    top = 0
    for i, r in enumerate(rows, 1):
        run += r["impressions"]
        if tot_i and run >= tot_i * 0.8:
            top = i
            break

    L = [
        "# Agronomy verification worklist",
        "",
        f"Generated by `tools/article_chem_audit.py` from `{src}`. "
        "Regenerate it, do not hand-edit.",
        "",
        f"- **{len(rows)}** article pages carry a chemical name or a dose",
        f"- **{sum(len(r['doses']) for r in rows)}** dose expressions, "
        f"**{sum(len(r['chemicals']) for r in rows)}** chemical mentions",
        f"- **{tot_i:,}** impressions across them in the GSC window",
        f"- **the first {top} pages are ~80% of that exposure** — check those "
        "first" if top else "",
        f"- **{len(watch)}** pages name a molecule whose Indian registration "
        "is restricted or contested (⚠ below)",
        "",
        "Every dose below was generated, not verified. Check each against an "
        "ICAR package of practices or the state agri-university recommendation "
        "for that crop, then correct it in the article's source module under "
        "`tools/articles/` and re-run `python tools/article_builder.py --all`. "
        "Correcting the built HTML directly is overwritten by the next build.",
        "",
        "The ⚠ list is a prompt, not an authority — confirm current status at "
        "cibrc.nic.in.",
        "",
        "---",
        "",
    ]
    for i, r in enumerate(rows, 1):
        L.append(f"## {i}. `{r['slug']}`")
        L.append("")
        L.append(f"- impressions **{r['impressions']:,}** · clicks "
                 f"{r['clicks']:,} · source `{r['module']}`")
        if r["watch"]:
            for w in r["watch"]:
                L.append(f"- ⚠ **{w}**")
        if r["chemicals"]:
            L.append(f"- chemicals: {', '.join(r['chemicals'])}")
        if r["doses"]:
            L.append(f"- doses: {' · '.join(r['doses'][:14])}"
                     + (" …" if len(r["doses"]) > 14 else ""))
        if r["claims"]:
            L.append("")
            L.append("  Sentences pairing a chemical with a dose — verify each:")
            for s in r["claims"][:8]:
                L.append(f"  - [ ] {s}")
        L.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    return f"{OUT.relative_to(ROOT)} — {len(rows)} pages, {tot_i:,} impressions"


if __name__ == "__main__":
    rows, src = audit()
    print(write(rows, src))
