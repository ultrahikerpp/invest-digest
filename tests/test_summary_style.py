"""Tests for the per-channel summary_style plumbing (gooaye_notes)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from backend import ai_provider, claude_browser, chatgpt_browser, card_generator
from runner import _get_channel_style


# ── Prompt selection in browser providers ─────────────────

@pytest.mark.parametrize("mod", [claude_browser, chatgpt_browser])
def test_generate_summary_uses_gooaye_prompt_when_style_set(mod, monkeypatch):
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["prompt"] = prompt
        return "摘要結果"

    monkeypatch.setattr(mod, "chat", fake_chat)
    mod.generate_summary("逐字稿", "EP999", summary_style="gooaye_notes")
    assert "投資心法" in captured["prompt"]
    assert "聽眾 QA" in captured["prompt"]


@pytest.mark.parametrize("mod", [claude_browser, chatgpt_browser])
def test_generate_summary_uses_generic_prompt_by_default(mod, monkeypatch):
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["prompt"] = prompt
        return "摘要結果"

    monkeypatch.setattr(mod, "chat", fake_chat)
    mod.generate_summary("逐字稿", "EP999")
    assert "核心觀點" in captured["prompt"]
    assert "投資心法" not in captured["prompt"]


@pytest.mark.parametrize("mod", [claude_browser, chatgpt_browser])
def test_generate_summary_fomo_sniff_still_works(mod, monkeypatch):
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["prompt"] = prompt
        return "摘要結果"

    monkeypatch.setattr(mod, "chat", fake_chat)
    mod.generate_summary("內文", "深入分析：某某主題")
    assert "情境預測與觸發條件" in captured["prompt"]


def test_gooaye_style_overrides_fomo_sniff(monkeypatch):
    # A gooaye episode mentioning 深入分析 early must not be mis-routed.
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["prompt"] = prompt
        return "摘要結果"

    monkeypatch.setattr(claude_browser, "chat", fake_chat)
    claude_browser.generate_summary(
        "今天來深入分析一下市場", "EP999", summary_style="gooaye_notes"
    )
    assert "投資心法" in captured["prompt"]


@pytest.mark.parametrize("mod", [claude_browser, chatgpt_browser])
def test_gooaye_style_uses_longer_chat_timeout(mod, monkeypatch):
    # Regression: gooaye notes are longer to generate; 180s made chat() fall
    # back to the stability check mid-thinking and grab UI status text.
    captured = {}

    def fake_chat(prompt, timeout_secs=180):
        captured["timeout_secs"] = timeout_secs
        return "摘要結果"

    monkeypatch.setattr(mod, "chat", fake_chat)
    mod.generate_summary("逐字稿", "EP999", summary_style="gooaye_notes")
    assert captured["timeout_secs"] == 600

    mod.generate_summary("逐字稿", "EP999")
    assert captured["timeout_secs"] == 180


# ── ai_provider passthrough ───────────────────────────────

def test_ai_provider_passes_summary_style_through(monkeypatch):
    captured = {}

    def fake_generate_summary(transcript, title, summary_style=None, host_name=None):
        captured["summary_style"] = summary_style
        return "摘要結果"

    monkeypatch.setattr(claude_browser, "generate_summary", fake_generate_summary)
    ai_provider.generate_summary("逐字稿", "EP999", provider="claude",
                                 summary_style="gooaye_notes")
    assert captured["summary_style"] == "gooaye_notes"


# ── runner channel-style lookup ───────────────────────────

def test_get_channel_style_returns_style_or_none():
    channels = [
        {"channel_id": "UC_GOOAYE", "name": "Gooaye 股癌", "summary_style": "gooaye_notes"},
        {"channel_id": "UC_OTHER", "name": "其他頻道"},
    ]
    assert _get_channel_style("UC_GOOAYE", channels) == "gooaye_notes"
    assert _get_channel_style("UC_OTHER", channels) is None
    assert _get_channel_style("UC_UNKNOWN", channels) is None
    assert _get_channel_style(None, channels) is None


# ── card section ordering ─────────────────────────────────

def test_ordered_sections_keeps_document_order_for_gooaye_notes():
    sections = {
        "本集主題總覽": "主題A\n主題B",
        "一、主題A：結論": "內容A",
        "二、主題B：結論": "內容B",
        "聽眾 QA": "Q內容",
        "投資心法": "心法內容",
        "提及標的": "標的內容",
    }
    ordered = card_generator.ordered_sections(sections)
    assert [k for k, _ in ordered] == list(sections.keys())


def test_ordered_sections_keeps_whitelist_order_for_generic_summaries():
    sections = {
        "核心觀點": "內容",
        "提及標的": "內容",
        "亂入章節": "不該出現",
        "風險提示": "內容",
    }
    ordered = card_generator.ordered_sections(sections)
    assert [k for k, _ in ordered] == ["核心觀點", "提及標的", "風險提示"]
