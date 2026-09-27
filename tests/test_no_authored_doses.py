"""We never author a pesticide, fertiliser or veterinary dose (LEGAL_RULES §2).

Asked for on 27 Sep 2026, after the audit found fertiliser and pesticide
amounts printed across ~100 article pages, the chat's saved answers, the crop
data files and the Khoj knowledge base. They were all rewritten to name the
product and the timing, and to send the farmer to the product label, the
Soil Health Card, the KVK / कृषि विभाग, or a registered vet for the amount.

This file keeps it that way: every surface a farmer reads is scanned with the
shared detector in backend/services/legal.py, the chat prompt must keep its
no-dose rule, and the chat's last-line redaction must keep working.

If a test here fails, the change is what is wrong. Never weaken, skip or delete
a test here to get a green build. A seed rate or a yield is not a dose, but
write it without a per-unit number ("एक एकड़ में 40 किलो बीज") so the detector
can stay strict.
"""

import re
from pathlib import Path

import pytest

from backend.services.legal import DOSE_RE, find_doses, redact_doses

ROOT = Path(__file__).resolve().parents[1]


def _visible(html: str) -> str:
    """Page text the way a reader (or Google) sees it: styles and non-schema
    scripts dropped, tags turned into spaces so table cells and fact cards
    that sit next to each other read as one phrase."""
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r'<script(?![^>]*ld\+json).*?</script>', " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _surfaces():
    """Everything a farmer can read that we wrote: article pages and their
    sources, the chat's curated and saved answers, the knowledge bases and
    the crop data files."""
    pats = [
        ("frontend", "**/*.html"), ("frontend", "*.js"),
        ("tools/articles", "*.py"), ("tools/seed_qa", "*.py"),
        ("backend/data", "**/*.json"),
    ]
    for base, pat in pats:
        for p in sorted((ROOT / base).glob(pat)):
            if "__pycache__" not in p.parts:
                yield p
    for rel in ("cache/seed_qa.json", "cache/cache_store.json",
                "data/agri_knowledge.json"):
        p = ROOT / rel
        if p.exists():
            yield p


SURFACES = list(_surfaces())


def test_there_is_something_to_scan():
    assert len(SURFACES) > 150


@pytest.mark.parametrize("path", SURFACES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_surface_prints_a_dose(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".html":
        text = _visible(text)
    doses = find_doses(text)
    assert not doses, (
        f"{path.relative_to(ROOT)} prints a dose: {doses[:3]}. Name the product "
        "and the timing, and send the farmer to the product label, the Soil "
        "Health Card, the KVK or a registered vet for the amount "
        "(backend/services/legal.py has the wording: DOSE_PESTICIDE, "
        "DOSE_FERTILISER, DOSE_VET)."
    )


# ── The detector itself ──────────────────────────────────────────────────────
DOSES = [
    "Propiconazole 25% EC — 1ml प्रति लीटर पानी",
    "यूरिया 25-30 kg प्रति एकड़",
    "25 किग्रा जिंक सल्फेट/हे.",
    "3 मि.ली. प्रति 10 लीटर पानी",
    "प्रति एकड़ 50 किलो यूरिया",
    "प्रति एकड़ लगभग 40-48 किलो नाइट्रोजन",
    "15 लीटर पानी में 30 मिली",
    "1 लीटर गोमूत्र में 10 मिली नीम तेल",
    "Celphos की 1 गोली प्रति क्विंटल",
    "120 kg per hectare",
    "Per acre: N-50kg, P-25kg",
    "Add 8–10 tons FYM/acre",
    "ಇದಕ್ಕೆ ಎಕರೆಗೆ 10 ಕೆಜಿ ಜಿಂಕ್",
    "Mancozeb 2.5 ಗ್ರಾಂ/ಲೀ",
    "Tricyclazole 0.6 ಗ್ರಾ/ಲೀ",
    "20 ಕೆಜಿ ಪ್ರತಿ ಎಕರೆ",
    "2 கிராம் ஒரு லிட்டர்",
]
NOT_DOSES = [
    "एक एकड़ में 40 किलो बीज",            # seed rate, said the allowed way
    "उपज 35-45 क्विंटल (एक हेक्टेयर में)",  # yield
    "भाव ₹2,275 प्रति क्विंटल",            # a price
    "10 क्विंटल माल भेजें तो प्रति क्विंटल ₹40",
    "नीम तेल प्रति टन 500 ग्राम यूरिया पर चढ़ाया जाता है",
    "कितनी खाद डालनी है, यह मृदा स्वास्थ्य कार्ड से तय करें",
]


@pytest.mark.parametrize("text", DOSES)
def test_detector_catches_a_dose(text):
    assert find_doses(text), text


@pytest.mark.parametrize("text", NOT_DOSES)
def test_detector_leaves_non_doses_alone(text):
    assert not find_doses(text), (text, find_doses(text))


# ── The chat ────────────────────────────────────────────────────────────────
def test_chat_prompt_forbids_doses():
    src = (ROOT / "backend/services/chatbot_service.py").read_text(encoding="utf-8")
    assert "NEVER give a quantity or dose" in src
    for word in ("pesticide", "fertiliser", "animal medicine", "label",
                 "Soil Health Card", "registered vet"):
        assert word in src, f"the chat's no-dose rule lost '{word}'"


@pytest.mark.parametrize("lang", ["hi", "en", "kn"])
def test_redaction_removes_every_dose_and_adds_the_referral(lang):
    answer = ("माहू दिखे तो Imidacloprid 17.8 SL — 0.5ml प्रति लीटर पानी का छिड़काव करें। "
              "यूरिया 25 kg प्रति एकड़ दें।")
    out = redact_doses(answer, lang)
    assert not DOSE_RE.search(out), out
    assert "KVK" in out
    assert "Imidacloprid" in out     # the product name stays; only the amount goes


def test_redaction_leaves_a_clean_answer_as_it_was():
    clean = "गेहूं में पहली सिंचाई 20-25 दिन पर करें।"
    assert redact_doses(clean) == clean


@pytest.mark.parametrize("rel", ["backend/routes/chatbot.py",
                                 "backend/services/news_auto_service.py"])
def test_ai_text_is_redacted_before_it_is_served(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    assert "from backend.services.legal import redact_doses" in src
    assert "redact_doses(" in src.split("import redact_doses", 1)[1]
