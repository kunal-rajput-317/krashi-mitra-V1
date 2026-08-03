"""utils/hindi_translit.py — the fix for the Devanagari-firm-name-note bug.

Two properties, matching the two callers documented in the module:

**slug_chars() must not change shape.** It backs services/dealers.py's
unique_slug(), which is a permanent id quoted by LeadClick.target_id. This is
the same function dealers.py always called, just moved — these tests pin its
exact output so a future "improvement" (e.g. adding schwa insertion here too)
cannot silently change what a new dealer's slug looks like.

**readable() must produce an actual name, not blanks.** This is the one that
was broken: services/upi.py's UPI note ran Hindi text through an ASCII-only
filter with no transliteration step first, so "शर्मा ट्रेडर्स" (a firm's real
name) became a wall of spaces. readable() exists so the note names the firm.
"""
import pytest

from backend.utils.hindi_translit import readable, slug_chars


class TestSlugCharsIsUnchanged:
    """Pinned to services/dealers.py's original behaviour before this module
    existed — moving the table must not have altered it."""

    def test_matches_the_previously_hardcoded_output(self):
        """Pinned to dealers.py's behaviour before _DEVA moved here — no schwa,
        so "शर्मा ट्रेडर्स" comes out consonant-run-together, not "sharma
        tredars". This is what unique_slug() has always turned into
        "shrma-tredrs-<district>", and that shape must not change."""
        assert slug_chars("शर्मा ट्रेडर्स") == "shrma tredrs"

    def test_no_inherent_vowel_is_inserted(self):
        """slug_chars() never adds a letter that was not in the mapping table
        — that is the whole difference from readable()."""
        assert slug_chars("गुप्ता") == "gupta"          # ग has no vowel sign attached: no inherent "a"
        assert slug_chars("नमक") == "nmk"                # three bare consonants: no vowels inserted at all

    def test_latin_and_digits_pass_through_untouched(self):
        assert slug_chars("Sharma Traders 2") == "Sharma Traders 2"

    def test_empty_and_none_are_safe(self):
        assert slug_chars("") == ""
        assert slug_chars(None) == ""


class TestReadableProducesAName:
    """The property the fix exists for."""

    def test_devanagari_name_is_not_blank(self):
        out = readable("शर्मा ट्रेडर्स")
        assert out.strip() != ""
        assert not out.isspace()

    def test_output_is_pure_ascii(self):
        """Must survive services/upi.py's UPI-note charset filter unchanged,
        or the note ends up truncated at the first non-ASCII byte."""
        for name in ("शर्मा ट्रेडर्स", "गुप्ता खाद बीज भंडार", "पटेल कृषि केंद्र",
                     "अग्रवाल फर्टिलाइजर", "श्री राम ट्रेडिंग कंपनी"):
            out = readable(name)
            assert out.isascii(), f"{name!r} -> {out!r} is not pure ASCII"

    @pytest.mark.parametrize("hindi,expect_word", [
        ("शर्मा ट्रेडर्स", "Sharma"),
        ("गुप्ता खाद बीज भंडार", "Gupta"),
        ("पटेल कृषि केंद्र", "Patel"),
        ("यादव बीज भंडार", "Yadav"),
        # Not "Singh" — सिंह has no consonant that reads "g"; "Singh" is a
        # fixed anglicisation convention, not a phonetic transliteration, and
        # would need a surname lookup table to reproduce. "Sinh" is still
        # recognisable, and the note never has to be the sole identifier —
        # it always travels with the slug, district and amount.
        ("सिंह किसान सेवा केंद्र", "Sinh"),
    ])
    def test_recognisable_words_survive(self, hindi, expect_word):
        assert expect_word in readable(hindi)

    def test_multi_word_names_keep_word_boundaries(self):
        """A single run-on string is as unreadable as blanks were — this is
        the property the word-final schwa-drop exists to protect."""
        out = readable("गुप्ता खाद बीज भंडार")
        assert out.count(" ") == 3, out

    def test_each_word_is_capitalised(self):
        out = readable("शर्मा ट्रेडर्स")
        for word in out.split(" "):
            assert word[0].isupper(), f"{word!r} in {out!r} is not capitalised"

    def test_mixed_hindi_and_latin(self):
        out = readable("श्री Ram Traders")
        assert "Ram Traders" in out

    def test_empty_and_none_are_safe(self):
        assert readable("") == ""
        assert readable(None) == ""

    def test_pure_punctuation_yields_empty_not_a_crash(self):
        assert readable("...---...") == "...---..."  # nothing to transliterate, passes through
