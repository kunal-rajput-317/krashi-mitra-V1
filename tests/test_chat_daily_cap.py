"""The temporary 3-questions-a-day cap on AI Chat.

Two halves have to agree: the server counter in `backend/utils/security.py`
(the one that actually protects the AI spend) and the browser counter in
`frontend/chat.html` (the one that shows the farmer a kind message). A test
here so the two cannot quietly drift apart when the cap is next changed.
"""

import re

import pytest

from backend.routes.chatbot import AI_CHAT_DAILY_LIMIT
from backend.utils import security


@pytest.fixture(autouse=True)
def fresh_counters():
    """Every test starts the day over, and with the per-minute window empty."""
    security._daily.clear()
    security._daily_date = ""
    security._hits.clear()
    yield
    security._daily.clear()
    security._daily_date = ""
    security._hits.clear()


def _ask(client, ip="203.0.113.7", q="गेहूं में यूरिया कब डालें?"):
    return client.post("/ask", json={"q": q}, headers={"X-Forwarded-For": ip})


class TestServerCap:
    def test_the_fourth_question_of_the_day_is_refused(self, client):
        for i in range(AI_CHAT_DAILY_LIMIT):
            r = _ask(client)
            assert r.status_code == 200, f"question {i + 1} refused: {r.text}"

        r = _ask(client)
        assert r.status_code == 429, r.text
        assert r.headers.get("X-Daily-Limit") == str(AI_CHAT_DAILY_LIMIT)
        assert int(r.headers["Retry-After"]) > 0

    def test_the_refusal_is_readable_hindi_not_a_bare_429(self, client):
        """The browser prints this string when it cannot read the header."""
        for _ in range(AI_CHAT_DAILY_LIMIT):
            _ask(client)
        detail = _ask(client).json()["detail"]
        assert str(AI_CHAT_DAILY_LIMIT) in detail
        assert re.search(r"[ऀ-ॿ]", detail), detail

    def test_one_farmer_running_out_does_not_cap_the_next(self, client):
        for _ in range(AI_CHAT_DAILY_LIMIT):
            _ask(client, ip="203.0.113.7")
        assert _ask(client, ip="203.0.113.7").status_code == 429
        assert _ask(client, ip="198.51.100.2").status_code == 200

    def test_the_counter_resets_when_the_date_rolls(self, client):
        for _ in range(AI_CHAT_DAILY_LIMIT):
            _ask(client)
        assert _ask(client).status_code == 429

        security._daily_date = "1999-01-01"   # next call sees a new IST day
        assert _ask(client).status_code == 200

    def test_an_hour_of_quiet_does_not_reset_it(self, client):
        """The sliding-window store prunes buckets after an hour of silence.
        The day counter lives in its own map precisely so it does not."""
        for _ in range(AI_CHAT_DAILY_LIMIT):
            _ask(client)
        security._prune(security.time.time() + 7200)
        assert _ask(client).status_code == 429


class TestBrowserHalfAgrees:
    def test_chat_html_counts_to_the_same_number(self, repo_root):
        src = (repo_root / "frontend" / "chat.html").read_text(encoding="utf-8")
        m = re.search(r"let CHAT_DAILY_LIMIT = (\d+);", src)
        assert m, "chat.html no longer declares CHAT_DAILY_LIMIT"
        assert int(m.group(1)) == AI_CHAT_DAILY_LIMIT, (
            "frontend/chat.html and AI_CHAT_DAILY_LIMIT disagree — change both"
        )

    def test_the_cap_message_exists_in_every_language(self, repo_root):
        src = (repo_root / "frontend" / "chat.html").read_text(encoding="utf-8")
        for key in ("cap_left", "cap_spent", "cap_placeholder"):
            assert src.count(f"{key}:") == 3, f"{key} missing from a language block"
