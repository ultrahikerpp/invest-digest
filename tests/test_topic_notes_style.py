"""Tests for the topic_notes summary style (游庭皓的財經皓角 / JC 趨勢財經觀點)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from backend import ai_provider, claude_browser, chatgpt_browser, card_generator, prompts, worker
from runner import _get_channel_host, _summary_matches_style


# ── Prompt builder ────────────────────────────────────────

def test_build_topic_notes_prompt_includes_host_title_transcript_and_sections():
    result = prompts.build_topic_notes_prompt("逐字稿內容 ABC", "2026/7/15 標題", "游庭皓")
    assert "逐字稿內容 ABC" in result
    assert "2026/7/15 標題" in result
    assert "游庭皓認為" in result
    assert "本集主題總覽" in result
    assert "關鍵數據" in result
    assert "投資觀念" in result
    assert "提及標的" in result


def test_build_topic_notes_prompt_falls_back_to_generic_host():
    result = prompts.build_topic_notes_prompt("逐字稿", "標題", None)
    assert "主持人認為" in result


# ── Prompt selection in browser providers ─────────────────

@pytest.mark.parametrize("mod", [claude_browser, chatgpt_browser])
def test_generate_summary_uses_topic_notes_prompt_when_style_set(mod, monkeypatch):
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["prompt"] = prompt
        return "摘要結果"

    monkeypatch.setattr(mod, "chat", fake_chat)
    mod.generate_summary("逐字稿", "EP1", summary_style="topic_notes", host_name="Jenny")
    assert "本集主題總覽" in captured["prompt"]
    assert "關鍵數據" in captured["prompt"]
    assert "Jenny認為" in captured["prompt"]
    assert "投資心法" not in captured["prompt"]  # gooaye-only section


@pytest.mark.parametrize("mod", [claude_browser, chatgpt_browser])
def test_topic_notes_overrides_fomo_sniff(mod, monkeypatch):
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["prompt"] = prompt
        return "摘要結果"

    monkeypatch.setattr(mod, "chat", fake_chat)
    mod.generate_summary("今天來深入分析一下市場", "標題",
                         summary_style="topic_notes", host_name="游庭皓")
    assert "本集主題總覽" in captured["prompt"]
    assert "情境預測與觸發條件" not in captured["prompt"]


@pytest.mark.parametrize("mod", [claude_browser, chatgpt_browser])
def test_topic_notes_uses_medium_timeout(mod, monkeypatch):
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["timeout_secs"] = timeout_secs
        return "摘要結果"

    monkeypatch.setattr(mod, "chat", fake_chat)
    mod.generate_summary("逐字稿", "EP1", summary_style="topic_notes")
    assert captured["timeout_secs"] == 300


# ── ai_provider / worker passthrough ──────────────────────

def test_ai_provider_passes_host_name_through(monkeypatch):
    captured = {}

    def fake_generate_summary(transcript, title, summary_style=None, host_name=None):
        captured["summary_style"] = summary_style
        captured["host_name"] = host_name
        return "摘要結果"

    monkeypatch.setattr(claude_browser, "generate_summary", fake_generate_summary)
    ai_provider.generate_summary("逐字稿", "EP1", provider="claude",
                                 summary_style="topic_notes", host_name="Jenny")
    assert captured["summary_style"] == "topic_notes"
    assert captured["host_name"] == "Jenny"


def test_worker_passes_host_name_through(monkeypatch):
    captured = {}

    def fake_generate_summary(transcript, title, provider="claude",
                              summary_style=None, host_name=None):
        captured["host_name"] = host_name
        return "摘要結果"

    monkeypatch.setattr(ai_provider, "generate_summary", fake_generate_summary)
    worker.generate_summary("逐字稿", "EP1", provider="claude",
                            summary_style="topic_notes", host_name="游庭皓")
    assert captured["host_name"] == "游庭皓"


# ── runner helpers ────────────────────────────────────────

def test_get_channel_host_returns_host_or_none():
    channels = [
        {"channel_id": "UC_HAO", "name": "游庭皓的財經皓角", "host_name": "游庭皓"},
        {"channel_id": "UC_OTHER", "name": "其他頻道"},
    ]
    assert _get_channel_host("UC_HAO", channels) == "游庭皓"
    assert _get_channel_host("UC_OTHER", channels) is None
    assert _get_channel_host("UC_UNKNOWN", channels) is None


TOPIC_NOTES_DOC = """### 本集主題總覽
- 主題A
### 一、主題A：結論
內容
### 關鍵數據
- 台股 45,201 點
### 投資觀念
本集未提及
### 提及標的
台積電
"""

GENERIC_DOC = """## 核心觀點
內容
## 關鍵數據
- 數字
## 風險提示
內容
"""

GOOAYE_DOC = """### 本集主題總覽
- 主題A
### 一、主題A
內容
### 聽眾 QA
Q內容
### 投資心法
- 心法
"""


def test_summary_matches_style_topic_notes():
    assert _summary_matches_style(TOPIC_NOTES_DOC, "topic_notes") is True
    assert _summary_matches_style(GENERIC_DOC, "topic_notes") is False
    assert _summary_matches_style(GOOAYE_DOC, "topic_notes") is False


def test_summary_matches_style_keeps_gooaye_separate():
    assert _summary_matches_style(GOOAYE_DOC, "gooaye_notes") is True
    assert _summary_matches_style(TOPIC_NOTES_DOC, "gooaye_notes") is False


# ── card section ordering compatibility ───────────────────

def test_ordered_sections_keeps_document_order_for_topic_notes():
    sections = {
        "本集主題總覽": "主題A\n主題B",
        "一、主題A：結論": "內容A",
        "二、主題B：結論": "內容B",
        "關鍵數據": "- 台股 45,201 點",
        "投資觀念": "本集未提及",
        "提及標的": "台積電",
    }
    ordered = card_generator.ordered_sections(sections)
    assert [k for k, _ in ordered] == list(sections.keys())
