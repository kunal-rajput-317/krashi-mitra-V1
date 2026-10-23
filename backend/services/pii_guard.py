# ============================================================
# services/pii_guard.py — keep Aadhaar numbers out of free text
#
# LEGAL_RULES §4a: we never store an Aadhaar number, "even partly". No form
# asks for one, but every free-text box (a Bazar post, a comment, a blue-tick
# note, an AI chat question) is one place a farmer can type it anyway — often
# helpfully, "मेरा आधार 2345 6789 0123 है, वेरिफ़ाई कर दो". So the number is
# masked before the row is written: database/db.py hooks mask_aadhaar() onto
# those columns, and routes/chatbot.py runs it before a question goes to the
# AI. Masking, not refusing — the post or question still goes through.
#
# A bare 12-digit match would also eat phone numbers, which sellers DO put in
# Bazar posts and must keep. Two things keep those safe:
#   * the Verhoeff check digit every real Aadhaar number carries — a random
#     12-digit number passes only 1 time in 10;
#   * a 12-digit run reading 91 + a mobile number (91 then 6-9) is treated as
#     a phone, as is anything written after a "+".
# ============================================================
import re
import unicodedata

MASK = "[आधार नंबर हटाया गया]"

# 4-4-4 with optional space/hyphen, or 12 in a row. \d also matches Devanagari
# (०-९) and other Indian-script digits; _ascii() reads them as numbers.
_AADHAAR_RE = re.compile(r"(?<![\d+])(\d{4})[ -]?(\d{4})[ -]?(\d{4})(?!\d)")

# Verhoeff tables (multiplication, permutation).
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def _ascii(digits: str) -> str:
    return "".join(str(unicodedata.digit(ch)) for ch in digits)


def _verhoeff_ok(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def looks_like_aadhaar(number: str) -> bool:
    """12 digits that could be a real Aadhaar number: no leading 0/1, and a
    valid check digit."""
    n = _ascii(number)
    return len(n) == 12 and n[0] not in "01" and _verhoeff_ok(n)


def mask_aadhaar(text):
    """`text` with every Aadhaar-like number replaced by MASK. None and
    non-strings pass through untouched, so it is safe on any column value."""
    if not text or not isinstance(text, str):
        return text

    def _sub(m):
        raw = m.group(0)
        n = _ascii(m.group(1) + m.group(2) + m.group(3))
        if raw.isdigit() and n.startswith("91") and n[2] in "6789":
            return raw          # 91 + a mobile number, written without the +
        return MASK if looks_like_aadhaar(n) else raw

    return _AADHAAR_RE.sub(_sub, text)
