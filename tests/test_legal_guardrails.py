"""Legal guardrails that no person or AI tool may quietly undo.

Asked for on 25 Sep 2026: "make sure we never do any illegal stuff, not even
by mistake — so that anyone, not even the AI I use, builds illegal stuff."
The written rules live in LEGAL_RULES.md at the repo root, and CLAUDE.md /
AGENTS.md make every AI coding tool load them. Written rules can be ignored,
so this file turns the checkable ones into failures that CI raises on every
push.

What the audit that day actually found, and what each test now prevents:

  * three live pages recommended pesticides India banned in 2023 (Dicofol on
    the chilli and litchi guides, Dinocap in the Khoj knowledge base);
  * /terms and /privacy-policy still said the blue tick meant "identity
    verified", a week after it became a paid premium badge — a paid mark
    described as a verification is a misleading claim;
  * /privacy-policy defined a child as under 13, while India's DPDP Act 2023
    says under 18 and /terms already said 18;
  * no page said KrashiMitra is not a government website, on a section titled
    "सरकारी योजना".

If one of these tests fails, the change is what is wrong. Never weaken, skip
or delete a test here to get a green build. If the government bans a new
pesticide, add it to BANNED below.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Pesticides banned for use in India ───────────────────────────────────────
# Sources: Supreme Court order on endosulfan (2011); the older banned list of
# the Central Insecticides Board & Registration Committee; the Insecticides
# (Prohibition) Order of 8 Aug 2018 (12 banned at once, 6 more from 31 Dec
# 2020); and the 2023 order banning dicofol, dinocap and methomyl.
BANNED = [
    "endosulfan", "aldrin", "chlordane", "heptachlor", "endrin", "toxaphene",
    "pentachlorophenol", "parathion", "nitrofen", "dibromochloropropane",
    "tetradifon", "chlorobenzilate", "maleic hydrazide", "ethylene dibromide",
    "metoxuron", "calcium cyanide", "lindane",
    # 2018 order
    "benomyl", "carbaryl", "diazinon", "fenarimol", "fenthion", "linuron",
    "sodium cyanide", "thiometon", "tridemorph", "trifluralin",
    "alachlor", "dichlorvos", "ddvp", "phorate", "phosphamidon", "triazophos",
    "trichlorfon",
    # 2023 order
    "dicofol", "dinocap", "methomyl",
]
BANNED_HI = [
    "एंडोसल्फान", "पैराथियान", "लिंडेन", "बेनोमिल", "कार्बारिल", "कार्बेरिल",
    "डायजिनॉन", "एलाक्लोर", "डाइक्लोरवास", "डीडीवीपी", "फोरेट", "फॉस्फामिडॉन",
    "ट्राइजोफॉस", "ट्रायजोफॉस", "ट्राइफ्लूरालिन", "डाइकोफॉल", "डाईकोफॉल",
    "मेथोमिल",
]
_BANNED_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(b) for b in BANNED) + r")(?![a-z])"
    + "|(" + "|".join(re.escape(b) for b in BANNED_HI) + ")",
    re.IGNORECASE,
)
# A banned name may appear only in a sentence that warns against it.
_WARNING_RE = re.compile(
    r"बचें|बचना|प्रतिबंध|मना है|banned|prohibited|avoid|ನಿಷೇಧ|ಬಳಸಬೇಡಿ|தடை",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"[।\n!?]|</(?:p|li|td|tr|div|h\d)>|<br\s*/?>")


def _site_files():
    pats = [
        ("frontend", "**/*.html"), ("frontend", "**/*.js"),
        ("backend/routes", "*.py"), ("backend/services", "*.py"),
        ("backend/data", "**/*.json"), ("tools/articles", "*.py"),
    ]
    for base, pat in pats:
        for p in (ROOT / base).glob(pat):
            if "__pycache__" not in p.parts:
                yield p


def test_no_banned_pesticide_is_recommended():
    offenders = []
    for path in _site_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not _BANNED_RE.search(text):
            continue
        for sentence in _SENTENCE_SPLIT.split(text):
            m = _BANNED_RE.search(sentence)
            if m and not _WARNING_RE.search(sentence):
                snippet = re.sub(r"<[^>]+>|\s+", " ", sentence).strip()[:120]
                offenders.append(f"{path.relative_to(ROOT)}: {m.group(0)!r} in {snippet!r}")
    assert not offenders, (
        "A pesticide banned in India is named as a remedy. Remove it and send "
        "the farmer to the label or कृषि विभाग / KVK instead:\n  "
        + "\n  ".join(offenders)
    )


# ── The blue tick is a paid badge, never an identity check ───────────────────
_TICK_AS_VERIFICATION = re.compile(
    r"नीला टिक[^।<]{0,80}पहचान (?:का|की) सत्यापन"
    r"|पहचान [^।<]{0,30}द्वारा सत्यापित"
    r"|सत्यापित विक्रेता"
    r"|verified seller",
    re.IGNORECASE,
)


def test_blue_tick_is_never_described_as_identity_verification():
    offenders = []
    for base, pat in [("frontend", "*.html"), ("frontend", "*.js"),
                      ("backend/routes", "*.py"), ("backend/services", "*.py")]:
        for path in (ROOT / base).glob(pat):
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if line.lstrip().startswith(("#", "//")):
                    continue  # comments may explain the old wording
                if _TICK_AS_VERIFICATION.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{n}")
    assert not offenders, (
        "The blue tick is a paid premium membership. Calling it identity "
        "verification is a misleading claim:\n  " + "\n  ".join(offenders)
    )


# ── Statements the legal pages must keep making ──────────────────────────────
def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_legal_pages_keep_required_statements():
    terms = _read("frontend/terms.html")
    privacy = _read("frontend/privacy-policy.html")
    yojana = _read("frontend/sarkari_yojana.html")

    assert "शिकायत अधिकारी" in terms, "/terms must name a Grievance Officer (IT Rules 2021)"
    assert "निजी वेबसाइट" in terms, "/terms must say we are a private website, not the government"
    assert "सरकारी वेबसाइट नहीं" in yojana, "/sarkari_yojana must say it is not a government website"
    assert "18 वर्ष" in terms and "18 वर्ष" in privacy, "both pages must set the account age at 18"
    assert "13 वर्ष" not in privacy, "a child is under 18 under the DPDP Act, not under 13"
    for page, name in [(terms, "terms"), (privacy, "privacy-policy")]:
        assert "krashimitra038@gmail.com" in page, f"/{name} must print the contact email"


def test_no_form_asks_for_aadhaar_or_bank_details():
    field = re.compile(
        r"""(?:name|id)=["'][^"']*(?:aadha|account_?num|acc_?no|ifsc|upi_?pin|card_?num|cvv)""",
        re.IGNORECASE,
    )
    offenders = []
    for base in ("frontend", "backend", "admin"):
        for pat in ("**/*.html", "**/*.js", "**/*.py"):
            for path in (ROOT / base).glob(pat):
                if "__pycache__" in path.parts:
                    continue
                if field.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "Never collect Aadhaar, bank account, card or UPI PIN details:\n  "
        + "\n  ".join(offenders)
    )


# ── Every AI tool is pointed at the rules ────────────────────────────────────
def test_ai_instruction_files_load_the_legal_rules():
    assert (ROOT / "LEGAL_RULES.md").is_file(), "LEGAL_RULES.md was deleted"
    assert "@LEGAL_RULES.md" in _read("CLAUDE.md"), "CLAUDE.md must import LEGAL_RULES.md"
    assert "LEGAL_RULES.md" in _read("AGENTS.md"), "AGENTS.md must point at LEGAL_RULES.md"
    assert "LEGAL_RULES.md" in _read(".github/copilot-instructions.md")
    assert "test_legal_guardrails.py" in _read("LEGAL_RULES.md")
