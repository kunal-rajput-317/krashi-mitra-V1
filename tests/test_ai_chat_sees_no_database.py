"""The AI chat's model never sees a database row (LEGAL_RULES §4).

What it may see: the question, the district the page sends, and our own crop
and knowledge files. Until 2 Oct 2026 /ask also loaded the last six
chat_history rows of whatever `user_id` the request body named, with no login
check, so anyone could post user_id=5 and have that farmer's messages put into
a prompt sent to Gemini and echoed back. These tests keep that door shut.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_prompt_builder_imports_nothing_from_the_database():
    tree = ast.parse((ROOT / "backend/services/chatbot_service.py").read_text(encoding="utf-8"))
    mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    bad = [m for m in mods if "database" in m or "sqlalchemy" in m]
    assert not bad, f"chatbot_service must not read the database: {bad}"


def test_a_user_id_in_the_body_puts_no_history_in_the_prompt(client, monkeypatch):
    from backend.routes import chatbot

    seen = {}

    def _capture(question, district, language, context, history):
        seen["history"] = history
        return "PROMPT"

    async def _no_model(prompt, max_tokens=1500):
        return "ठीक है", "gemini"

    monkeypatch.setattr(chatbot, "build_prompt", _capture)
    monkeypatch.setattr(chatbot, "call_ai", _no_model)
    monkeypatch.setattr(chatbot, "_CACHE_AVAILABLE", False)
    monkeypatch.setattr(chatbot, "_RAG_AVAILABLE", False)
    monkeypatch.setattr(chatbot, "get_setting", lambda key, default=None: True)

    r = client.post("/ask", json={"q": "गेहूं की बुवाई कब करें", "user_id": 1})
    assert r.status_code == 200, r.text
    assert seen.get("history") == ""
