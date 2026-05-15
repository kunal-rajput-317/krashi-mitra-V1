# ============================================================
# services/search_service.py
# Krishi Mitra — Agriculture Search Engine
#
# Strategy: pure keyword matching + relevance scoring
#   - No heavy AI / RAG needed at this stage
#   - Reads JSON files from backend/data/crops/
#   - Scores every entry against the query
#   - Returns top results sorted by score
#
# Future: swap score() with a vector similarity call (RAG-ready)
# ============================================================

import json
import os
import re
from typing import List, Dict

# ── Path to crop data directory ──────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "crops")

# ── In-memory cache: loaded once, reused across requests ─────
_CROP_CACHE: Dict[str, dict] = {}


# ── Hindi stopwords to strip before scoring ──────────────────
# Romanized synonym map — expands tokens before scoring
QUERY_SYNONYMS = {
    "buwai":  ["sowing", "बुवाई"],
    "buwaya": ["sowing", "बुवाई"],
    "buai":   ["sowing", "बुवाई"],
    "ropai":  ["transplanting", "रोपाई"],
    "ilaj":   ["treatment", "उपचार"],
    "upay":   ["treatment", "prevention"],
    "khad":   ["fertilizer", "urea", "dap"],
    "bimari": ["disease", "रोग"],
    "rog":    ["disease", "बीमारी"],
    "lagana": ["sowing", "planting"],
    "kab":    ["season", "time"],
}

HINDI_STOPWORDS = {
    "का", "की", "के", "में", "से", "है", "हैं", "और", "या", "पर",
    "को", "ने", "कि", "एक", "यह", "वह", "इस", "उस", "जो", "भी",
    "तो", "हो", "कर", "रहा", "रही", "रहे", "था", "थी", "थे",
    "कौन", "सी", "कब", "क्या", "कैसे", "कितना", "कितनी",
    "me", "ka", "ki", "ke", "se", "hai", "aur", "ya", "par",
    "ko", "ek", "yeh", "voh", "jo", "bhi", "to", "ho", "kar",
    "kab", "kaun", "kya", "kaise", "kitna",
}

# ── Romanized → Devanagari crop aliases ──────────────────────
CROP_ALIASES = {
    "gehu":      ["gehu", "गेहूँ", "गेहु", "wheat", "गेहूं"],
    "dhaan":     ["dhaan", "dhan", "धान", "rice", "paddy", "चावल"],
    "ganna":     ["ganna", "ganne", "गन्ना", "गन्ने", "sugarcane", "ikh"],
    "sarson":    ["sarson", "सरसों", "mustard", "sarso"],
    "aloo":      ["aloo", "आलू", "potato", "alu"],
}

# Reverse map: any alias → canonical key
_ALIAS_TO_KEY = {}
for key, aliases in CROP_ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_KEY[alias.lower()] = key


def _load_all_crops() -> List[dict]:
    """Load all JSON files from data/crops/ into memory (cached)."""
    global _CROP_CACHE
    crops = []

    if not os.path.isdir(DATA_DIR):
        return crops

    for fname in os.listdir(DATA_DIR):
        if not fname.endswith(".json"):
            continue
        key = fname.replace(".json", "")
        if key in _CROP_CACHE:
            crops.append(_CROP_CACHE[key])
            continue
        path = os.path.join(DATA_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _CROP_CACHE[key] = data
                crops.append(data)
        except Exception as e:
            print(f"[search_service] Could not load {fname}: {e}")

    return crops


def _normalize(text: str) -> List[str]:
    """Lowercase, remove punctuation, split into tokens, strip stopwords."""
    text = text.lower().strip()
    text = re.sub(r"[।,.!?;:()\[\]\"']", " ", text)
    tokens = text.split()
    result = []
    for t in tokens:
        if t in HINDI_STOPWORDS:
            continue
        if len(t) <= 1:
            continue
        result.append(t)
        # Expand romanized synonyms
        for syn in QUERY_SYNONYMS.get(t, []):
            result.append(syn.lower())
    return result


def _score_entry(entry: dict, query_tokens: List[str], query_raw: str) -> int:
    """
    Score one result entry against the query tokens.
    Higher = more relevant.

    Scoring weights:
      +15  exact name/title match (substring)
      +10  keyword list match
      +5   symptoms / description match
      +3   treatment / prevention match
      +2   any field match
    """
    score = 0
    q_raw = query_raw.lower()

    # Collect all searchable text fields
    name       = (entry.get("name", "") + " " + entry.get("name_en", "")).lower()
    keywords   = " ".join(entry.get("keywords", [])).lower()
    symptoms   = entry.get("symptoms", "").lower()
    treatment  = entry.get("treatment", "").lower()
    prevention = entry.get("prevention", "").lower()
    description= entry.get("description", "").lower()
    all_text   = f"{name} {keywords} {symptoms} {treatment} {prevention} {description}"

    for token in query_tokens:
        if token in name:        score += 10
        if token in keywords:    score += 8
        if token in symptoms:    score += 5
        if token in treatment:   score += 3
        if token in prevention:  score += 3
        if token in description: score += 2
        if token in all_text:    score += 1  # catch-all

    # Bonus: multi-token phrase match in name
    if len(query_tokens) >= 2:
        phrase = " ".join(query_tokens[:2])
        if phrase in name:     score += 8
        if phrase in keywords: score += 5

    return score


def _extract_crop_filter(query_tokens: List[str], explicit_filter: str) -> str:
    """
    Detect crop name inside the query itself, or use the explicit filter chip.
    Returns canonical crop key (e.g. 'gehu') or '' for all crops.
    """
    if explicit_filter:
        return _ALIAS_TO_KEY.get(explicit_filter.lower(), explicit_filter.lower())

    for token in query_tokens:
        if token in _ALIAS_TO_KEY:
            return _ALIAS_TO_KEY[token]
    return ""


def _flatten_crop(crop_data: dict) -> List[dict]:
    """
    Flatten one crop JSON into a list of scorable entries:
      - one entry per disease
      - one entry per fertilizer
      - one general entry for sowing info
    """
    entries = []
    crop_name = crop_data.get("crop", "")
    crop_key  = crop_data.get("crop_en", crop_name).lower()
    crop_icon_key = crop_data.get("crop_key", crop_key)

    # ── Diseases ──────────────────────────────────────────────
    for d in crop_data.get("diseases", []):
        entries.append({
            "type":       "disease",
            "crop":       crop_name,
            "crop_key":   crop_icon_key,
            "name":       d.get("name", ""),
            "name_en":    d.get("name_en", ""),
            "keywords":   d.get("keywords", []),
            "symptoms":   d.get("symptoms", ""),
            "treatment":  d.get("treatment", ""),
            "prevention": d.get("prevention", ""),
            "score":      0,
        })

    # ── Fertilizers ───────────────────────────────────────────
    for f in crop_data.get("fertilizers", []):
        entries.append({
            "type":        "fertilizer",
            "crop":        crop_name,
            "crop_key":    crop_icon_key,
            "name":        f.get("name", ""),
            "name_en":     f.get("name_en", ""),
            "keywords":    f.get("keywords", []),
            "description": f.get("description", ""),
            "dosage":      f.get("dosage", ""),
            "season":      f.get("season", ""),
            "score":       0,
        })

    # ── Sowing info ───────────────────────────────────────────
    sowing = crop_data.get("sowing", {})
    if sowing:
        entries.append({
            "type":        "sowing",
            "crop":        crop_name,
            "crop_key":    crop_icon_key,
            "name":        sowing.get("title", f"{crop_name} बुवाई जानकारी"),
            "name_en":     sowing.get("title_en", f"{crop_key} sowing info"),
            "keywords":    sowing.get("keywords", []),
            "description": sowing.get("description", ""),
            "season":      sowing.get("season", ""),
            "treatment":   sowing.get("variety", ""),   # reuse field for recommended varieties
            "score":       0,
        })

    return entries


def search_agriculture(query: str, crop_filter: str = "", lang: str = "hindi") -> List[dict]:
    """
    Main search function.
    Returns list of result dicts, sorted by relevance score, top 6 max.
    """
    query_tokens  = _normalize(query)
    detected_crop = _extract_crop_filter(query_tokens, crop_filter)

    all_crops   = _load_all_crops()
    all_entries = []

    for crop_data in all_crops:
        # Apply crop filter if detected
        if detected_crop:
            crop_key = crop_data.get("crop_en", "").lower()
            crop_aliases = CROP_ALIASES.get(detected_crop, [detected_crop])
            if not any(alias.lower() in crop_key for alias in crop_aliases):
                continue

        entries = _flatten_crop(crop_data)
        all_entries.extend(entries)

    if not all_entries:
        return []

    # Score every entry
    scored = []
    for entry in all_entries:
        s = _score_entry(entry, query_tokens, query)
        if s > 0:
            entry["score"] = s
            scored.append(entry)

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Return top 6
    return scored[:6]