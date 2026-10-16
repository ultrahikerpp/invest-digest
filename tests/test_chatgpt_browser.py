"""Regression tests for ChatGPT browser response completion checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import chatgpt_browser


def test_generation_running_checks_chatgpt_streaming_markers():
    class Page:
        def evaluate(self, script):
            self.script = script
            return True

    page = Page()

    assert chatgpt_browser._generation_running(page) is True
    assert "stop-button" in page.script
    assert "data-is-streaming" in page.script


def test_wait_for_stable_response_ignores_text_while_generation_is_running(monkeypatch):
    running_states = iter([True, True, True] + [False] * 10)
    response_calls = 0

    def response_text(_page):
        nonlocal response_calls
        response_calls += 1
        return "partial" if response_calls <= 3 else "complete"

    monkeypatch.setattr(
        chatgpt_browser,
        "_generation_running",
        lambda page: next(running_states),
        raising=False,
    )
    monkeypatch.setattr(
        chatgpt_browser,
        "_extract_last_response",
        response_text,
    )
    monkeypatch.setattr(chatgpt_browser.time, "time", lambda: 0)
    monkeypatch.setattr(chatgpt_browser.time, "sleep", lambda _: None)

    result = chatgpt_browser._wait_for_stable_response(object(), timeout_secs=10)

    assert result == "complete"


def test_wait_for_stable_response_returns_empty_when_streaming_times_out(monkeypatch):
    clock = iter([0, 0, 0, 0, 2])
    monkeypatch.setattr(chatgpt_browser, "_generation_running", lambda page: True, raising=False)
    monkeypatch.setattr(chatgpt_browser, "_extract_last_response", lambda page: "partial")
    monkeypatch.setattr(chatgpt_browser.time, "time", lambda: next(clock))
    monkeypatch.setattr(chatgpt_browser.time, "sleep", lambda _: None)

    result = chatgpt_browser._wait_for_stable_response(object(), timeout_secs=1)

    assert result == ""


def test_generate_summary_rejects_incomplete_gooaye_response(monkeypatch):
    monkeypatch.setattr(
        chatgpt_browser,
        "chat",
        lambda prompt, timeout_secs=180: (
            "## 本集主題總覽\n主題\n\n"
            "## 一、主題重點\n內容在句子中途"
        ),
    )

    result = chatgpt_browser.generate_summary(
        "逐字稿", "EP666", summary_style="gooaye_notes"
    )

    assert "ChatGPT 瀏覽器摘要失敗" in result
    assert "投資心法" in result


def test_generate_summary_accepts_complete_gooaye_response(monkeypatch):
    complete = "\n\n".join(
        [
            "## 本集主題總覽\n主題",
            "## 一、主題重點\n內容",
            "## 聽眾 QA\n本集未提及",
            "## 投資心法\n- 心法",
            "## 提及標的\n台積電",
        ]
    )
    monkeypatch.setattr(
        chatgpt_browser,
        "chat",
        lambda prompt, timeout_secs=180: complete,
    )

    result = chatgpt_browser.generate_summary(
        "逐字稿", "EP666", summary_style="gooaye_notes"
    )

    assert result.startswith(complete)
    assert "負責任 AI 聲明" in result
