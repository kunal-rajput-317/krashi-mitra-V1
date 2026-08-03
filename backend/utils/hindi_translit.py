# ============================================================
# utils/hindi_translit.py
# Devanagari → Latin, in the two shapes this codebase actually needs.
#
# Most dealer and firm names arrive in Hindi. A plain "keep only ASCII" filter
# — which is what services/upi.py's note sanitiser (_NOTE_SAFE) does on its
# own — drops every character of a Devanagari string, one space per character,
# leaving a wall of blanks instead of a name. That is the bug this module
# exists to fix.
#
# TWO CALLERS, TWO SHAPES, DELIBERATELY NOT SHARED:
#
#   slug_chars()     — services/dealers.py::_slugify. Character-for-character
#                       substitution, no inserted vowels. The output is a URL
#                       component and a permanent id (LeadClick.target_id quotes
#                       it), never shown to a farmer, so "sharmaa-tredarsa" —
#                       what naive schwa insertion would produce here — buys
#                       nothing. Existing slugs must not change shape underfoot.
#
#   readable()       — services/upi.py's payment note and the /pay page's
#                       display fallback. This one IS read by a human: on a UPI
#                       confirmation screen and in a bank statement weeks later.
#                       "sharma-tredars" there reads as broken, not as a name.
#
# readable() inserts the inherent Hindi vowel a consonant carries when it has
# no vowel sign, virama or nukta attached — and drops it at the end of a word,
# matching spoken Hindi's schwa deletion for the common case. It is not a
# linguistically complete schwa-deletion engine (mid-word consonant clusters,
# e.g. केंद्र, are a known harder case — see test_hindi_translit.py) and does
# not try to be: the result only has to be recognisable to the dealer reading
# it, never the sole identifier — the slug, district and amount travel with it.
# ============================================================
import re

# Not a transliteration standard and not trying to be — see module docstring
# for why slug_chars() and readable() are allowed to read differently off the
# same table.
DEVA = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "अं": "an",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
    # Vowel signs (मात्रा).
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    # Silent/among-consonant marks: drop rather than guess.
    "्": "", "ं": "n", "ः": "", "ँ": "n", "़": "",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

_CONSONANTS = frozenset("कखगघङचछजझञटठडढणतथदधनपफबभमयरलळवशषसह"
                        ) | {"क़", "ख़", "ग़", "ज़", "ड़", "ढ़", "फ़"}
_VOWEL_SIGNS = frozenset("ािीुूृेैोौ")
# What stops a consonant from carrying its own implicit "a": an explicit vowel
# sign supplies its own vowel instead, virama (्) conjuncts it with the next
# consonant, nukta (़) changes the consonant's own sound rather than following
# it with one.
_BLOCKS_INHERENT_VOWEL = _VOWEL_SIGNS | {"्", "़"}


def slug_chars(text: str) -> str:
    """Character-for-character substitution, no inserted vowels. See module
    docstring — this is services/dealers.py's slug behaviour, unchanged."""
    return "".join(DEVA.get(ch, ch) for ch in (text or ""))


def readable(text: str) -> str:
    """A human-readable Latin rendering, title-cased word by word.

    Falls back to slug_chars()-style behaviour for any character with no
    special handling (Latin letters, digits, punctuation pass through as-is),
    so a mixed Hindi/English name transliterates only the Hindi part.
    """
    text = text or ""
    out = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch in _CONSONANTS:
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt in _BLOCKS_INHERENT_VOWEL:
                out.append(DEVA[ch])                    # vowel/virama/nukta follows — no schwa
            elif nxt in ("", " "):
                out.append(DEVA[ch])                     # word-final — schwa deletes in speech
            else:
                out.append(DEVA[ch] + "a")                # mid-word before another letter — schwa stays
        else:
            out.append(DEVA.get(ch, ch))
    s = re.sub(r"\s+", " ", "".join(out)).strip()
    return " ".join(w[:1].upper() + w[1:] for w in s.split(" ") if w)
