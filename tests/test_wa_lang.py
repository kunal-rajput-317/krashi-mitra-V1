# ============================================================
# tests/test_wa_lang.py
# The WhatsApp channel post is written in the language its followers speak.
#
# The defect: krashimitra_kerala went out in Hindi — not the wrong dialect,
# the wrong language and the wrong script. Ten of the thirty-one channels were
# doing it. These tests hold the fix at both ends:
#
#   • every claimed state's post comes out in ONE script, all the way through
#     — heading, crops, source line and call to action. A post that is
#     Malayalam at the top and Devanagari at the bottom is not fixed, it is
#     half fixed, and that is what a per-string fallback quietly produces when
#     a block is incomplete.
#   • the /bhav guard did not move. services/state_lang must still refuse
#     every non-Devanagari language, because the reason it refuses them —
#     index bloat against zero search demand — has not changed. This file
#     exists precisely so that adding Malayalam to the channel cannot be
#     mistaken for permission to add it to 14,000 URLs.
# ============================================================
import re

import pytest

from backend.services import state_lang, wa_channels, wa_lang, wa_style

# Where each script lives, so "is this line in the right language?" is a
# question about code points rather than about eyeballing a screenshot.
_BLOCKS = {
    "Devanagari": (0x0900, 0x097F),
    "Bengali":    (0x0980, 0x09FF),   # Bengali and Assamese share it
    "Assamese":   (0x0980, 0x09FF),
    "Gurmukhi":   (0x0A00, 0x0A7F),
    "Gujarati":   (0x0A80, 0x0AFF),
    "Odia":       (0x0B00, 0x0B7F),
    "Tamil":      (0x0B80, 0x0BFF),
    "Telugu":     (0x0C00, 0x0C7F),
    "Kannada":    (0x0C80, 0x0CFF),
    "Malayalam":  (0x0D00, 0x0D7F),
}

_LANGS = sorted(wa_lang._load())


def _script_of(ch: str) -> str | None:
    for name, (lo, hi) in _BLOCKS.items():
        if lo <= ord(ch) <= hi:
            return name
    return None


def _indic(text: str) -> set:
    """Every Indic script present in a string, Bengali/Assamese folded together
    since they are one block and nothing can tell them apart by code point."""
    out = set()
    for ch in text:
        s = _script_of(ch)
        if s:
            out.add("Bengali" if s == "Assamese" else s)
    return out


def _lines(lang: str, n: int = 3) -> list:
    hi = ["गेहूं", "प्याज", "आलू", "धान", "टमाटर"][:n]
    return [{"name": wa_lang.crop(h, lang), "avg": 2000 + 100 * i,
             "pct": [1.3, -7.2, 0.0][i % 3],
             "move": wa_style.move_text([1.3, -7.2, 0.0][i % 3], lang),
             "rank": i, "p_hi": 2500 + 100 * i, "top_market": "Palakkad",
             "w_lo": 1900 + 100 * i, "w_hi": 2400 + 100 * i}
            for i, h in enumerate(hi)]


def _ctx(lang: str, state_en: str, hi_state: str) -> dict:
    return {"state": wa_lang.state_name(state_en, lang, hi_state),
            "slug": "x", "lang": lang,
            "bhav": wa_lang.word("bhav", lang, "मंडी भाव"),
            "date": wa_lang.date_str(23, 9, 2026, lang, "23 सितंबर 2026"),
            "mandis": 269, "market": "Palakkad",
            "url": "https://krashimitra.in/bhav/rajya/x"}


class TestTheGuardDidNotMove:
    """/bhav is still Devanagari-only. This is the whole reason for two files."""

    def test_state_lang_still_refuses_every_other_script(self):
        assert set(state_lang.loaded()) == {"mr"}

    def test_a_channel_language_is_invisible_to_bhav_pages(self):
        for lang in _LANGS:
            assert not state_lang.is_local(lang), lang
            assert state_lang.html_lang(lang) == "hi"
            assert state_lang.og_locale(lang) == "hi_IN"
            # and the crop name a /bhav page prints is untouched
            assert state_lang.crop("गेहूं", lang) == "गेहूं"

    def test_marathi_is_not_duplicated(self):
        """One Marathi, in state_lang, delegated to — not a second copy here."""
        assert "mr" not in wa_lang._load()
        assert wa_lang.lang_for("Maharashtra") == "mr"
        assert wa_lang.crop("गेहूं", "mr") == "गहू"
        assert wa_lang.pack("wa", "mr") == state_lang.pack("wa", "mr")


class TestEveryChannelIsRouted:

    def test_the_ten_states_that_were_posting_in_hindi(self):
        want = {"Kerala": "ml", "Tamil Nadu": "ta", "Karnataka": "kn",
                "Andhra Pradesh": "te", "Telangana": "te", "West Bengal": "bn",
                "Tripura": "bn", "Gujarat": "gu", "Punjab": "pa",
                "Odisha": "or", "Assam": "as"}
        for state, lang in want.items():
            assert wa_lang.lang_for(state) == lang, state

    def test_the_hindi_belt_is_untouched(self):
        """Hindi is those channels' native language, not a fallback. If one of
        these ever changes, it is a decision, not a side effect."""
        for state in ("Uttar Pradesh", "Madhya Pradesh", "Bihar", "Rajasthan",
                      "Haryana", "Chhattisgarh", "Jharkhand", "Uttarakhand",
                      "Himachal Pradesh", "NCT of Delhi", "Chandigarh",
                      "Jammu and Kashmir"):
            assert wa_lang.lang_for(state) == "hi", state

    def test_every_claimed_state_has_a_channel(self):
        """A language block for a state with no channel is dead weight that
        nobody will ever see be wrong."""
        keyed = set(wa_channels._spec().get("channels") or {})
        for state in wa_lang.states():
            assert wa_channels._key(state) in keyed, state

    def test_an_unknown_state_is_hindi_not_a_crash(self):
        assert wa_lang.lang_for("Atlantis") == "hi"
        assert wa_lang.lang_for("") == "hi"
        assert wa_lang.lang_for(None or "") == "hi"


@pytest.mark.parametrize("lang", _LANGS)
class TestOnePostIsOneLanguage:

    def test_every_format_and_tone_stays_in_one_script(self, lang):
        """The real failure mode of a per-string fallback: a Malayalam heading
        over a Hindi call to action. Composed across all 30 combinations,
        because a gap in one tone's block only shows on the days that tone is
        up."""
        script = wa_lang._load()[lang]["script"]
        want = "Bengali" if script == "Assamese" else script
        state_en = (wa_lang._load()[lang].get("states") or ["X"])[0]
        ctx = _ctx(lang, state_en, "राज्य")
        lines = _lines(lang)
        for fmt in (f["id"] for f in wa_style.FORMATS):
            for tone in (t["id"] for t in wa_style.TONES):
                text = wa_style.compose(ctx, lines, fmt, tone)
                assert _indic(text) == {want}, f"{lang}/{fmt}/{tone}: {text}"

    def test_the_month_name_is_translated(self, lang):
        script = wa_lang._load()[lang]["script"]
        want = "Bengali" if script == "Assamese" else script
        for month in range(1, 13):
            out = wa_lang.date_str(8, month, 2026, lang, "8 सितंबर 2026")
            assert out.startswith("8 ") and out.endswith(" 2026")
            assert _indic(out) == {want}, (lang, month, out)

    def test_the_state_is_named_in_its_own_language(self, lang):
        script = wa_lang._load()[lang]["script"]
        want = "Bengali" if script == "Assamese" else script
        for state_en in (wa_lang._load()[lang].get("states") or ()):
            out = wa_lang.state_name(state_en, lang, "केरल")
            assert _indic(out) == {want}, (lang, state_en, out)

    def test_every_crop_key_is_a_hindi_name(self, lang):
        """Keys are the HINDI name, because bhav._hindi_name() has already
        folded every Agmarknet spelling onto one before crop() is called. A key
        typed in the local script would simply never match."""
        for hi_name, local in (wa_lang._load()[lang].get("crops") or {}).items():
            assert _indic(hi_name) == {"Devanagari"}, (lang, hi_name)
            assert local.strip()

    def test_no_template_carries_an_unknown_placeholder(self, lang):
        """A stray {crp} costs that one wording and silently falls back — which
        is the right behaviour at runtime and a bug worth catching here."""
        allowed = {"state", "bhav", "date", "n", "market", "crop", "price",
                   "pct", "lo", "hi", "names", "title"}
        for key, val in (wa_lang._load()[lang].get("wa") or {}).items():
            found = set(re.findall(r"\{(\w*)\}", val))
            assert found <= allowed, (lang, key, found - allowed)

    def test_the_source_credit_still_names_agmarknet(self, lang):
        """Translating the sentence around it must never translate away the
        attribution — the figures are the government's and the post says so."""
        blk = wa_lang._load()[lang]["wa"]
        for key, val in blk.items():
            if key.endswith(".credit"):
                assert "Agmarknet" in val and "data.gov.in" in val, (lang, key)


class TestNothingHereMovesANumber:

    def test_prices_are_identical_in_every_language(self):
        """wa_style may only arrange words. Switching the language is the
        newest way to reach that code, so it gets the same assertion the
        format×tone rotation already has."""
        want = None
        for lang in ["hi"] + _LANGS:
            text = wa_style.compose(_ctx(lang, "Kerala", "केरल"),
                                    _lines(lang), "suchi", "seedha")
            got = re.findall(r"₹[\d,]+", text)
            want = want if want is not None else got
            assert got == want, lang

    def test_the_link_is_untouched_by_translation(self):
        for lang in ["hi"] + _LANGS:
            text = wa_style.compose(_ctx(lang, "Kerala", "केरल"),
                                    _lines(lang), "suchi", "seedha")
            assert text.rstrip().endswith("https://krashimitra.in/bhav/rajya/x")


class TestItNeverRaisesAndNeverInvents:

    def test_a_missing_file_is_hindi(self, monkeypatch, tmp_path):
        monkeypatch.setattr(wa_lang, "_PATH", tmp_path / "gone.json")
        monkeypatch.setattr(wa_lang, "_cache", None)
        monkeypatch.setattr(wa_lang, "_mtime", -1.0)
        assert wa_lang._load() == {}
        assert wa_lang.lang_for("Kerala") == "hi"
        assert wa_lang.crop("गेहूं", "ml") == "गेहूं"
        assert wa_lang.state_name("Kerala", "ml", "केरल") == "केरल"

    def test_a_corrupt_file_is_hindi(self, monkeypatch, tmp_path):
        bad = tmp_path / "wa_lang.json"
        bad.write_text("{ not json", encoding="utf-8")
        monkeypatch.setattr(wa_lang, "_PATH", bad)
        monkeypatch.setattr(wa_lang, "_cache", None)
        monkeypatch.setattr(wa_lang, "_mtime", -1.0)
        assert wa_lang._load() == {}
        assert wa_lang.word("bhav", "ml", "मंडी भाव") == "मंडी भाव"

    def test_an_untranslated_crop_keeps_its_hindi_name(self):
        assert wa_lang.crop("कटहल", "ml") == "कटहल"
        assert wa_lang.crop("", "ml") == ""

    def test_an_unknown_market_prints_in_latin_outside_devanagari(self):
        """कोच्चि inside a Malayalam sentence is a third language in the
        message. "Kochi" is what a Kerala newspaper prints."""
        assert wa_lang.district("कोच्चि", "ml", raw="Kochi") == "Kochi"
        # …but a Devanagari language keeps the Devanagari spelling it had
        assert wa_lang.district("सोलापुर", "mr", raw="Solapur") == "सोलापूर"
        # …and with nothing to fall back to, nothing is invented
        assert wa_lang.district("कोच्चि", "ml") == "कोच्चि"


class TestThePanelCanTellTheLanguageApart:

    def test_loaded_covers_both_files(self):
        got = wa_lang.loaded()
        assert "mr" in got and "ml" in got
        assert all(v.strip() for v in got.values())

    def test_every_label_is_written_in_its_own_language(self):
        """The chip on the admin card says മലയാളം, not "Malayalam" — the owner
        is reading the same alphabet he is about to paste."""
        for lang, blk in wa_lang._load().items():
            script = blk["script"]
            want = "Bengali" if script == "Assamese" else script
            assert _indic(blk["label"]) == {want}, lang
