"""Gemini keys are discovered from the environment, never listed in code.

Every free Gemini key carries its own daily quota, so the spares are the whole
reason the chat, the WhatsApp picture, the festival image and the news image
generators keep answering after the first key returns 429. The key list used to
be hardcoded — five copies of ("GEMINI_API_KEY", "GEMINI_API_KEY2",
"GEMINI_API_KEY3") in five files — which meant a fourth key silently did
nothing until someone remembered all five. These tests say a new key is an env
var and nothing else.
"""

import os
import re
from pathlib import Path

import pytest

from backend.services.chatbot_service import gemini_keys

REPO = Path(__file__).resolve().parents[1]

ALL_SLOTS = ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY{n}" for n in range(2, 10)] \
            + [f"GEMINI_API_KEY_{n}" for n in range(2, 10)]


@pytest.fixture
def clean_env(monkeypatch):
    for name in ALL_SLOTS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_five_keys_are_all_found_in_order(clean_env):
    clean_env.setenv("GEMINI_API_KEY", "k1")
    for n in range(2, 6):
        clean_env.setenv(f"GEMINI_API_KEY{n}", f"k{n}")
    assert [k for _, k in gemini_keys()] == ["k1", "k2", "k3", "k4", "k5"]


def test_a_sixth_key_needs_no_code_change(clean_env):
    """The point of the whole exercise: 5 is not a ceiling."""
    clean_env.setenv("GEMINI_API_KEY", "k1")
    for n in range(2, 8):
        clean_env.setenv(f"GEMINI_API_KEY{n}", f"k{n}")
    assert len(gemini_keys()) == 7


def test_gaps_and_blanks_are_skipped(clean_env):
    clean_env.setenv("GEMINI_API_KEY", "k1")
    clean_env.setenv("GEMINI_API_KEY2", "   ")   # slot exists, not filled yet
    clean_env.setenv("GEMINI_API_KEY5", "k5")    # 3 and 4 never set
    assert [k for _, k in gemini_keys()] == ["k1", "k5"]


def test_duplicate_key_counted_once(clean_env):
    """Pasting the same key into two slots buys no quota, so it must not look
    like two keys on /admin/status."""
    clean_env.setenv("GEMINI_API_KEY", "same")
    clean_env.setenv("GEMINI_API_KEY3", "same")
    assert len(gemini_keys()) == 1


def test_underscore_spelling_still_works(clean_env):
    clean_env.setenv("GEMINI_API_KEY_2", "k2")
    assert [k for _, k in gemini_keys()] == ["k2"]


def test_unrelated_gemini_vars_are_not_keys(clean_env):
    clean_env.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    clean_env.setenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    clean_env.setenv("GEMINI_TIMEOUT", "15")
    assert gemini_keys() == []


def test_no_module_hardcodes_its_own_key_list():
    """One discovery helper. A second list is a key that works everywhere but
    one place, found only under quota pressure."""
    offenders = []
    pat = re.compile(r"GEMINI_API_KEY_?\d")
    for py in (REPO / "backend").rglob("*.py"):
        if "__pycache__" in py.parts or py.name == "chatbot_service.py":
            continue  # the helper itself is allowed to spell the names out
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                offenders.append(f"{py.relative_to(REPO)}:{i}: {line.strip()}")
    assert not offenders, (
        "numbered Gemini keys named outside the discovery helper:\n"
        + "\n".join(offenders)
    )


def test_render_yaml_declares_the_spare_slots():
    txt = (REPO / "render.yaml").read_text(encoding="utf-8")
    for n in range(2, 6):
        assert f"GEMINI_API_KEY{n}" in txt, f"render.yaml does not mention key {n}"
