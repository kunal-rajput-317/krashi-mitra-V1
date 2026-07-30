"""Pure helpers behind the /bhav pages and the AI fallback chain.

These are cheap to test and expensive to get wrong: _slugify feeds every
canonical URL in the sitemap, _rupee is the number a farmer quotes at the
mandi, and the AI chain's config defaults decide which model answers.
"""

import pytest

from backend.routes import bhav
from backend.services import chatbot_service


class TestSlugify:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Sri Ganganagar", "sri-ganganagar"),
            ("Bengal Gram(Gram)", "bengal-gram-gram"),
            ("  Padded  Name  ", "padded-name"),
            ("Already-Slugged", "already-slugged"),
            ("", ""),
        ],
    )
    def test_slugs(self, raw, expected):
        assert bhav._slugify(raw) == expected

    def test_slug_is_url_safe(self):
        """Anything non-alphanumeric must collapse, or canonical URLs break."""
        slug = bhav._slugify("Aloo/Potato (Red) — 50% Grade #1")
        assert all(ch.isalnum() or ch == "-" for ch in slug)
        assert "--" not in slug
        assert not slug.startswith("-") and not slug.endswith("-")

    def test_slugify_is_stable(self):
        """Re-slugging a slug must be a no-op, or URLs drift between runs."""
        once = bhav._slugify("Sri Ganganagar")
        assert bhav._slugify(once) == once


class TestNumberFormatting:
    @pytest.mark.parametrize(
        "raw, expected",
        [("2606.43", 2606.43), ("1,250", 1250.0), (0, None), ("-5", None),
         ("", None), (None, None), ("abc", None)],
    )
    def test_num_parses_or_rejects(self, raw, expected):
        assert bhav._num(raw) == expected

    def test_rupee_rounds_and_groups(self):
        """Agmarknet reports fractional paise that mean nothing at a mandi."""
        assert bhav._rupee("2606.43") == "₹2,606"
        assert bhav._rupee("1250") == "₹1,250"

    def test_rupee_escapes_unparseable_input(self):
        """The raw value is echoed into HTML — it must not carry markup."""
        out = bhav._rupee("<script>alert(1)</script>")
        assert "<script>" not in out


class TestStateSvgSlug:
    @pytest.mark.parametrize(
        "state, expected",
        [
            ("Keralam", "kerala"),            # Agmarknet's spelling
            ("Chattisgarh", "chhattisgarh"),  # missing 'h'
            ("NCT of Delhi", "delhi"),
            ("Pondicherry", "puducherry"),
            ("Uttar Pradesh", "uttar_pradesh"),
        ],
    )
    def test_known_spellings_normalise(self, state, expected):
        assert bhav._state_svg_slug(state) == expected

    def test_every_slug_resolves_to_a_real_svg(self, repo_root):
        """The override table exists to match files on disk — prove it does."""
        svg_dir = repo_root / "frontend" / "images" / "state_map_svgs"
        on_disk = {p.stem for p in svg_dir.glob("*.svg")}
        for state in ("Keralam", "Chattisgarh", "NCT of Delhi",
                      "Pondicherry", "Uttar Pradesh", "Jammu and Kashmir"):
            assert bhav._state_svg_slug(state) in on_disk, state


class TestHindiDataDate:
    def test_converts_agmarknet_format(self):
        assert bhav._hindi_data_date("11/07/2026") == "11 जुलाई"

    @pytest.mark.parametrize("junk", ["", None, "not-a-date", "2026-07-11"])
    def test_unparseable_passes_through_safely(self, junk):
        assert isinstance(bhav._hindi_data_date(junk), str)


class TestAiFallbackConfig:
    @staticmethod
    def _inline_gemini_default() -> str:
        """The literal fallback baked into call_gemini's get_setting call."""
        import inspect
        import re

        source = inspect.getsource(chatbot_service.call_gemini)
        match = re.search(
            r'get_setting\(\s*"gemini_model"\s*,\s*"([^"]+)"', source
        )
        assert match, "call_gemini no longer has an inline gemini_model default"
        return match.group(1)

    def test_inline_default_is_an_allowed_model(self):
        """call_gemini used to fall back to gemini-1.5-flash, which is not on
        the allowlist — so which model answered depended on whether the
        admin setting had resolved."""
        from backend.config import ALLOWED_GEMINI_MODELS

        assert self._inline_gemini_default() in ALLOWED_GEMINI_MODELS

    def test_inline_default_matches_the_resolved_setting(self, monkeypatch):
        """With GEMINI_MODEL unset, both paths must pick the same model."""
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        resolved = chatbot_service.get_setting("gemini_model", "sentinel-unset")
        assert resolved == self._inline_gemini_default()

    def test_claude_default_is_an_allowed_model(self):
        from backend.config import ALLOWED_CLAUDE_MODELS, get_setting

        assert get_setting("claude_model", "") in ALLOWED_CLAUDE_MODELS

    def test_unavailable_message_is_never_cached(self):
        """AI_UNAVAILABLE_MSG must trip the bad-answer filter.

        Otherwise the outage message gets written into the semantic cache and
        served as a real answer long after the outage ends.
        """
        msg = chatbot_service.AI_UNAVAILABLE_MSG
        assert any(p.lower() in msg.lower()
                   for p in chatbot_service.BAD_ANSWER_PHRASES)
        assert chatbot_service.is_good_answer(msg) is False


class TestOllamaReachability:
    def test_localhost_is_fine_on_a_dev_box(self, monkeypatch):
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        assert chatbot_service.ollama_is_reachable() is True

    def test_localhost_is_skipped_on_render(self, monkeypatch):
        """Nothing listens on the dyno's 11434; calling it burns a 60s
        connect timeout before returning the same error anyway."""
        monkeypatch.setenv("RENDER", "srv-abc123")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        assert chatbot_service.ollama_is_reachable() is False

    @pytest.mark.parametrize(
        "url", ["http://127.0.0.1:11434", "http://0.0.0.0:11434",
                "http://host.docker.internal:11434"],
    )
    def test_all_loopback_spellings_are_caught(self, monkeypatch, url):
        monkeypatch.setenv("RENDER", "srv-abc123")
        monkeypatch.setenv("OLLAMA_BASE_URL", url)
        assert chatbot_service.ollama_is_reachable() is False

    def test_a_real_host_is_allowed_on_render(self, monkeypatch):
        monkeypatch.setenv("RENDER", "srv-abc123")
        monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.dev")
        assert chatbot_service.ollama_is_reachable() is True


class TestAnswerQuality:
    def test_substantive_answer_accepted(self):
        answer = (
            "गेहूं की बुवाई के समय DAP डालें। प्रति एकड़ 50 किलो पर्याप्त है, "
            "और यूरिया पहली सिंचाई के बाद डालें।"
        )
        assert chatbot_service.is_good_answer(answer) is True

    @pytest.mark.parametrize("bad", ["", "   ", "I cannot help with that.",
                                     "As an AI, I don't know."])
    def test_empty_or_refusal_answers_rejected(self, bad):
        assert chatbot_service.is_good_answer(bad) is False
