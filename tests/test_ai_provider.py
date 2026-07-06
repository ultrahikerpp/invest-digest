import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from backend import ai_provider


def test_unknown_provider_raises_value_error():
    with pytest.raises(ValueError, match="Unknown provider"):
        ai_provider._mod("gemini")


def test_claude_provider_resolves_to_claude_browser_module():
    mod = ai_provider._mod("claude")
    assert mod.__name__ == "backend.claude_browser"


def test_chatgpt_provider_resolves_to_chatgpt_browser_module():
    mod = ai_provider._mod("chatgpt")
    assert mod.__name__ == "backend.chatgpt_browser"


def test_generate_summary_dispatches_to_selected_provider(monkeypatch):
    calls = []

    class FakeModule:
        @staticmethod
        def generate_summary(transcript, title):
            calls.append((transcript, title))
            return "fake summary"

    monkeypatch.setattr(ai_provider, "_mod", lambda provider: FakeModule)

    result = ai_provider.generate_summary("transcript text", "title text", provider="chatgpt")

    assert result == "fake summary"
    assert calls == [("transcript text", "title text")]


def test_chat_dispatches_with_timeout(monkeypatch):
    calls = []

    class FakeModule:
        @staticmethod
        def chat(prompt, timeout_secs=180):
            calls.append((prompt, timeout_secs))
            return "fake response"

    monkeypatch.setattr(ai_provider, "_mod", lambda provider: FakeModule)

    result = ai_provider.chat("hello", timeout_secs=30, provider="claude")

    assert result == "fake response"
    assert calls == [("hello", 30)]
