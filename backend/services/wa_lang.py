# ============================================================
# services/wa_lang.py
# चैनल की भाषा — which language a state's WhatsApp post is WRITTEN in.
#
# THE DEFECT THIS FIXES: krashimitra_kerala's daily post went out in Hindi.
# Not a wrong-dialect problem like the Marathi round — a wrong-LANGUAGE one.
# A Malayali farmer opening a channel he joined because it says Kerala on it
# found प्याज — ₹6,575 ▲ 1.3%, five lines of a script he does not read, under
# a heading in a language he does not speak. The same was true of Tamil Nadu,
# Karnataka, Andhra, Telangana, Bengal, Gujarat, Punjab, Odisha and Assam:
# ten of the thirty-one channels were broadcasting in a language their
# followers did not choose.
#
# WHY THIS IS NOT services/state_lang
# -----------------------------------
# state_lang drops every non-Devanagari block on load, deliberately, and that
# guard must stay. Its evidence was that 0 of 1,841 SEARCH queries used another
# Indic script, so Tamil or Malayalam /bhav URLs would be index bloat against
# no demand — and index bloat is the site's diagnosed bottleneck.
#
# That finding is about search. A channel is not search. The follower already
# chose Kerala when he joined; nothing here is crawled, ranked, or given a URL.
# So the two surfaces get two answers and two files, and the /bhav guard is
# left exactly as strict as it was. This module never touches a page.
#
# WHERE EACH STRING COMES FROM, in order:
#   1. data/wa_lang.json          — the channel-only languages (this file's own)
#   2. data/state_lang.json       — Marathi, which /bhav serves too; delegated
#                                   so there is one Marathi and not two
#   3. the Hindi in services/wa_style — per string, for anything missing
#
# THE ONE GUARANTEE, same as state_lang's: nothing here raises and nothing here
# invents. A missing file, a corrupt file, an unknown state, an untranslated
# crop and a typo'd placeholder all resolve to today's Hindi behaviour. Being
# silent in Malayalam costs a reader; being wrong in Malayalam costs the number
# its trust.
#
# Pure functions, no FastAPI/DB import — same contract as state_lang.py.
#
# Runnable manually:  python -m backend.services.wa_lang
# ============================================================
import json
from pathlib import Path

from backend.services import state_lang

_PATH = Path(__file__).resolve().parents[1] / "data" / "wa_lang.json"

HINDI = state_lang.HINDI

# The scripts a post may be written in that are NOT Devanagari. A market or
# district name we have no translation for prints in Latin rather than in
# Devanagari for these: "Lasalgaon" inside a Malayalam sentence reads as a
# place name, कोच्चि reads as a third language turning up in the same message.
_LATIN_FALLBACK = True

_cache: dict | None = None
_mtime: float = -1.0


def _load() -> dict:
    """{lang_code: block} for this file's channel-only languages.

    No script guard, on purpose — that is the entire difference between this
    module and state_lang, and the header says why. The only requirement is
    that a block is an object; anything else is dropped rather than served."""
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {}
    if _cache is None or m != _mtime:
        try:
            raw = json.loads(_PATH.read_text(encoding="utf-8"))
            langs = raw.get("languages") or {}
            _cache = {c: b for c, b in langs.items() if isinstance(b, dict)}
        except Exception:                                  # noqa: BLE001
            _cache = {}
        _mtime = m
    return _cache or {}


def _mine(lang: str) -> dict:
    """This file's block for `lang`, or {} when it belongs to state_lang."""
    return _load().get(lang) or {}


def is_local(lang: str) -> bool:
    """True when `lang` is a real language rather than the Hindi default —
    whichever of the two files it lives in."""
    return bool(lang) and lang != HINDI and (lang in _load() or state_lang.is_local(lang))


def lang_for(state: str) -> str:
    """Language code for a state as the Agmarknet feed spells it.

    This file is asked first and state_lang second, so a state claimed here
    cannot be quietly overridden by a /bhav decision made for other reasons.
    Everything unclaimed returns Hindi — which is the right answer for the
    twelve Hindi-belt channels, not a fallback."""
    if not state:
        return HINDI
    want = state.strip()
    for code, blk in _load().items():
        if want in (blk.get("states") or ()):
            return code
    return state_lang.lang_for(state)


def pack(name: str, lang: str) -> dict:
    """A whole named block of flat strings — {} when absent.

    The shape services/wa_style and services/wa_extra want: the post needs a
    couple of dozen wordings at once and resolves its own fallbacks key by key,
    so handing the block over once beats two dozen round trips."""
    blk = _mine(lang).get(name)
    if isinstance(blk, dict):
        return dict(blk)
    return state_lang.pack(name, lang)


def word(key: str, lang: str, default: str = "") -> str:
    """One UI string, falling back to the Hindi the caller already had."""
    v = (_mine(lang).get("words") or {}).get(key)
    if isinstance(v, str) and v.strip():
        return v
    return state_lang.word(key, lang, default)


def crop(hi_name: str, lang: str) -> str:
    """Local crop name, or the Hindi name unchanged.

    Keyed on the HINDI name, exactly as state_lang.crop() is, because
    bhav._hindi_name() has already folded every Agmarknet spelling of a
    commodity onto one Hindi string before this is called — so one entry
    covers "Wheat", "Wheat(Desi)" and whatever the feed sends next.

    An untranslated crop keeps its Hindi name. In a Devanagari language that
    still reads; in Malayalam it is one word in the wrong script, which is a
    smaller failure than guessing at a translation for a crop nobody has
    checked. The fix for it is one line in the JSON, not code."""
    if not hi_name:
        return hi_name
    v = (_mine(lang).get("crops") or {}).get(hi_name.strip())
    if v:
        return v
    return state_lang.crop(hi_name, lang)


def state_name(en_state: str, lang: str, default: str) -> str:
    """The state's name in its own language — കേരളം, not केरल.

    It is the first word of the post's heading, so it is the loudest single
    tell that a message is or is not written for the person reading it.
    `default` is the caller's Hindi name, which is what every unclaimed state
    keeps."""
    v = (_mine(lang).get("state_names") or {}).get((en_state or "").strip())
    return v if isinstance(v, str) and v.strip() else default


def date_str(day: int, month: int, year: int, lang: str, default: str) -> str:
    """"23 സെപ്റ്റംബർ 2026" rather than "23 सितंबर 2026".

    Falls back to the caller's Hindi string on a table that is missing or not
    twelve long — a half-translated calendar would print one month in one
    language beside another in a second."""
    months = _mine(lang).get("months")
    if isinstance(months, list) and len(months) == 12 and 1 <= month <= 12:
        return f"{day} {months[month - 1]} {year}"
    return state_lang.date_str(day, month, year, lang, default)


def district(hi_name: str, lang: str, raw: str = "") -> str:
    """A district or market name in the post's language.

    Three answers, in order: a translation if the language has one; the feed's
    own Latin spelling if the language is not Devanagari; the Hindi otherwise.

    The middle case is the one worth spelling out. `hi_name` arrives already
    converted to Hindi by /bhav's table, and dropping कोच्चि into a Malayalam
    sentence puts a third language in the message. "Kochi" does not — a Latin
    place name inside an Indic sentence is what a Kerala newspaper prints."""
    if not hi_name:
        return hi_name
    blk = _mine(lang)
    if blk:
        v = (blk.get("districts") or {}).get(hi_name.strip())
        if v:
            return v
        if _LATIN_FALLBACK and blk.get("script") != "Devanagari" and raw:
            return raw
        return hi_name
    return state_lang.district(hi_name, lang)


def loaded() -> dict:
    """{code: label} for every language a channel post can be written in —
    this file's plus state_lang's. For an admin panel or a boot log."""
    out = {c: (b.get("label") or c) for c, b in _load().items()}
    out.update(state_lang.loaded())
    return out


def states() -> dict:
    """{english_state: lang_code} for the states this file claims. The panel
    and the tests both want to see the map rather than probe it state by
    state."""
    return {s: code for code, blk in _load().items()
            for s in (blk.get("states") or ())}


if __name__ == "__main__":  # pragma: no cover
    from backend.services import wa_channels

    print(f"{len(_load())} channel-only languages + {len(state_lang.loaded())} "
          f"from state_lang\n")
    for code, label in sorted(loaded().items()):
        print(f"  {code}  {label}")
    print()
    for key, row in sorted((wa_channels._spec().get("channels") or {}).items()):
        lg = lang_for(row.get("state") or "")
        print(f"  {key:20} {lg:3} {loaded().get(lg, 'हिन्दी')}")
