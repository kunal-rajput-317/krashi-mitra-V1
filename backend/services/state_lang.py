# ============================================================
# services/state_lang.py
# Which language a /bhav page should speak, given the state it is about.
#
# THE DEFECT THIS FIXES: a Maharashtra farmer types "बाजार भाव", not "मंडी भाव",
# and "गहू", not "गेहूं". /bhav had exactly one voice — a hardcoded hi_IN and
# मंडी भाव on all ~14,000 pages — so his query matched the page's DATA but not
# its WORDS. Measured over the 28 days to 3 Sep 2026: the Marathi mandi queries
# (अकोला सोयाबीन बाजार भाव आजचे, सोयाबीन बाजार भाव जालना, गहू बाजार भाव आजचे
# सोलापूर, मका बाजार भाव सोलापूर) all rank at positions 6-10 and earn ZERO
# clicks. The pages are already there and already ranking; they answer in the
# wrong dialect. This is the same mechanism as the script-mismatch round that
# named 92 crops and 737 districts in Hindi — carried one step further, from
# "the right script" to "the right word".
#
# DEVANAGARI ONLY, AND THAT IS ENFORCED, NOT ADVISED
# --------------------------------------------------
# Expanding /bhav into more languages was rejected on 2026-08-24, on evidence
# that 0 of 1,841 queries used any non-Devanagari Indic script. Marathi is
# Devanagari, so that finding never tested it — which is the whole reason this
# module is allowed to exist. To keep the exception from quietly becoming the
# rule, _load() REFUSES any language carrying characters from another Indic
# block. A well-meant Tamil or Kannada block added to the JSON is dropped on
# load rather than served. Those two are settled: they get articles.
#
# NO NEW URLS. This changes what an existing page says, never its address. The
# site's diagnosed problem is too many URLs, not too few; a /mr/ prefix would
# double 14,000 of them and make it worse.
#
# THE ONE GUARANTEE, same as services/crop_types.py: nothing here raises and
# nothing here invents. A missing file, a corrupt file, an unknown state, a
# crop with no translation or a template with a typo'd placeholder all resolve
# to today's Hindi behaviour. Being silent in Marathi is a missed click; being
# wrong in Marathi is a farmer who stops trusting the number too.
#
# Pure functions, no FastAPI/DB import — same contract as msp.py.
# ============================================================
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "state_lang.json"

HINDI = "hi"                       # the default voice; not a key in the file

# Indic blocks that are NOT Devanagari. Presence of any of these in a language
# block is taken as proof it is outside this module's remit — see the header.
_FOREIGN_BLOCKS = (
    (0x0980, 0x09FF),   # Bengali / Assamese
    (0x0A00, 0x0A7F),   # Gurmukhi
    (0x0A80, 0x0AFF),   # Gujarati
    (0x0B00, 0x0B7F),   # Odia
    (0x0B80, 0x0BFF),   # Tamil
    (0x0C00, 0x0C7F),   # Telugu
    (0x0C80, 0x0CFF),   # Kannada
    (0x0D00, 0x0D7F),   # Malayalam
)

_cache: dict | None = None
_mtime: float = -1.0


def _foreign_script(node) -> bool:
    """True if any string anywhere under `node` sits in a non-Devanagari Indic
    block. Walks the whole subtree rather than sampling: the giveaway could sit
    in one crop name inside an otherwise plausible block."""
    if isinstance(node, str):
        return any(lo <= ord(ch) <= hi for ch in node for lo, hi in _FOREIGN_BLOCKS)
    if isinstance(node, dict):
        return any(_foreign_script(v) for v in node.values())
    if isinstance(node, list):
        return any(_foreign_script(v) for v in node)
    return False


def _load() -> dict:
    """{lang_code: block} for every language that passes the script guard."""
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return {}
    if _cache is None or m != _mtime:
        try:
            raw = json.loads(_PATH.read_text(encoding="utf-8"))
            langs = raw.get("languages") or {}
            _cache = {
                code: blk for code, blk in langs.items()
                if isinstance(blk, dict)
                and blk.get("script") == "Devanagari"
                and not _foreign_script(blk)
            }
        except Exception:
            _cache = {}
        _mtime = m
    return _cache or {}


def lang_for(state: str) -> str:
    """Language code for a state name as the Agmarknet feed spells it.

    Returns HINDI for everything not explicitly claimed, so every page outside
    the listed states renders byte-identically to before this module existed.
    """
    if not state:
        return HINDI
    want = state.strip()
    for code, blk in _load().items():
        if want in (blk.get("states") or ()):
            return code
    return HINDI


def is_local(lang: str) -> bool:
    """True when `lang` is a real loaded language rather than the Hindi default.
    Call sites read better as `if state_lang.is_local(lang):` than as a
    comparison against a sentinel."""
    return bool(lang) and lang != HINDI and lang in _load()


def html_lang(lang: str) -> str:
    return (_load().get(lang, {}).get("html_lang") or "hi") if is_local(lang) else "hi"


def og_locale(lang: str) -> str:
    return (_load().get(lang, {}).get("og_locale") or "hi_IN") if is_local(lang) else "hi_IN"


def crop(hi_name: str, lang: str) -> str:
    """Local crop name, or the Hindi name unchanged.

    Keyed on the HINDI name because _hindi_name() has already folded every
    Agmarknet spelling of a commodity onto one Hindi string before this is
    called — so a single entry covers "Wheat", "Wheat(Desi)" and whatever the
    feed sends next. An untranslated crop keeps its Hindi name, which a Marathi
    reader still reads fine; a mistranslated one is the Turnip → अरहर bug in a
    second language.
    """
    if not is_local(lang) or not hi_name:
        return hi_name
    return (_load()[lang].get("crops") or {}).get(hi_name.strip()) or hi_name


def date_str(day: int, month: int, year: int, lang: str, default: str) -> str:
    """"8 सप्टेंबर 2026" rather than Hindi's "8 सितंबर 2026".

    The month name is the loudest single tell that a page is not written in the
    reader's language — it sits in the meta description, right at the front,
    where the SERP shows it. Falls back to the caller's Hindi string on a table
    that is missing or not twelve long, since a half-translated calendar would
    print a Hindi month next to a Marathi one.
    """
    if not is_local(lang):
        return default
    months = _load()[lang].get("months") or []
    if len(months) != 12 or not 1 <= month <= 12:
        return default
    return f"{day} {months[month - 1]} {year}"


def district(hi_name: str, lang: str) -> str:
    """Local district spelling, or the Hindi one unchanged.

    The same lookup as crop(), and it exists for the same measured reason one
    level down: the page printed सोलापुर while the query in GSC reads सोलापूर.
    Hindi and Marathi share the script and disagree on the vowel, the retroflex
    ळ and the nuqta — so a district name can be "already in Devanagari" and
    still not be the string the farmer typed.
    """
    if not is_local(lang) or not hi_name:
        return hi_name
    return (_load()[lang].get("districts") or {}).get(hi_name.strip()) or hi_name


def word(key: str, lang: str, default: str = "") -> str:
    """One UI string, falling back to the Hindi the caller already had."""
    if not is_local(lang):
        return default
    return (_load()[lang].get("words") or {}).get(key) or default


def _fill(template: str, vals: dict) -> str | None:
    """Format one template, or None if it cannot be filled.

    A template is copy, and copy is edited by hand in a JSON file by someone who
    is not looking at this module. A stray {crp} must therefore cost that one
    wording and nothing else — never a 500 on a page that was working.
    """
    try:
        out = template.format(**vals)
    except (KeyError, IndexError, ValueError):
        return None
    return " ".join(out.split()).strip(" —-·,") or None


def fill(key: str, lang: str, vals: dict, default: str = "") -> str:
    """One `words` entry formatted with `vals` — for a phrase that is copy but
    whose presence is a conditional, like "सरासरी ₹X/क्विंटल (₹lo ते ₹hi)" versus
    the sentence shown when a district reported no min/max at all. The choice of
    which belongs in the caller (it is data, not language); the wording of each
    belongs here (it is language, not data)."""
    if not is_local(lang):
        return default
    return _fill((_load()[lang].get("words") or {}).get(key) or "", vals) or default


def variants(kind: str, page: str, lang: str, vals: dict) -> list[str]:
    """Formatted `titles`/`descs` variants for a page type, richest first.

    Returns [] for Hindi and for anything the file does not define, which is the
    caller's signal to use its own Hindi variants — so a page type nobody has
    translated yet keeps working untouched.
    """
    if not is_local(lang):
        return []
    src = (_load()[lang].get(kind) or {}).get(page) or []
    out = [f for f in (_fill(t, vals) for t in src if isinstance(t, str)) if f]
    return out


def h1(page: str, lang: str, vals: dict, default: str) -> str:
    """The visible headline. Falls back to the caller's Hindi H1.

    A page whose Marathi title won the click and whose H1 then says मंडी भाव has
    spent the click to show the farmer he is in the wrong place — the headline
    has to move with the title or neither should.
    """
    if not is_local(lang):
        return default
    return _fill((_load()[lang].get("h1") or {}).get(page) or "", vals) or default


def faqs(page: str, lang: str, vals: dict) -> list[tuple[str, str]]:
    """Visible Q&A pairs, which are also the FAQPage JSON-LD source.

    Returns [] when undefined so the caller keeps its Hindi list. Pairs are
    dropped individually if either half fails to fill: half a Q&A is worse than
    none, and the JSON-LD would carry the same hole.
    """
    if not is_local(lang):
        return []
    out = []
    for pair in ((_load()[lang].get("faqs") or {}).get(page) or []):
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            continue
        q, a = _fill(str(pair[0]), vals), _fill(str(pair[1]), vals)
        if q and a:
            out.append((q, a))
    return out


def pack(name: str, lang: str) -> dict:
    """A whole named block of flat strings for a language — {} when absent.

    word() is the right shape for a page that needs one string at a time and
    already has the Hindi in hand. It is the wrong shape for the WhatsApp post,
    which needs a couple of dozen wordings at once and resolves its own
    fallbacks key by key (services/wa_style._s). Handing over the block once
    saves that caller two dozen round trips through is_local().

    Returns a copy of what the JSON holds and nothing else: absent language,
    absent block and a block that is not an object all give {}, so a caller can
    treat "no translation" and "no such language" as the same case — which they
    are, and the answer to both is Hindi."""
    if not is_local(lang):
        return {}
    blk = _load()[lang].get(name)
    return dict(blk) if isinstance(blk, dict) else {}


def loaded() -> dict:
    """{code: label} for the languages that survived the script guard — for an
    admin panel or a boot log to show what is actually live."""
    return {code: (blk.get("label") or code) for code, blk in _load().items()}
