import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import prompts


def test_build_summary_prompt_includes_title_and_transcript():
    result = prompts.build_summary_prompt("逐字稿內容 ABC", "EP999 測試標題")
    assert "EP999 測試標題" in result
    assert "逐字稿內容 ABC" in result
    assert "核心觀點" in result


def test_build_gooaye_summary_prompt_includes_title_transcript_and_sections():
    result = prompts.build_gooaye_summary_prompt("逐字稿內容 ABC", "EP999 | 🎮")
    assert "EP999 | 🎮" in result
    assert "逐字稿內容 ABC" in result
    assert "本集主題總覽" in result
    assert "聽眾 QA" in result
    assert "投資心法" in result
    assert "提及標的" in result
    # 名詞小教室 was explicitly excluded by user decision
    assert "名詞小教室" not in result


def test_build_fomo_analysis_prompt_includes_scenario_sections():
    result = prompts.build_fomo_analysis_prompt("深入分析內容", "深入分析標題")
    assert "深入分析標題" in result
    assert "情境預測與觸發條件" in result


def test_build_hashtag_prompt_includes_summary_body():
    result = prompts.build_hashtag_prompt("摘要重點內容")
    assert "摘要重點內容" in result
    assert "hashtag" in result


def test_build_analysis_prompt_includes_json_schema():
    result = prompts.build_analysis_prompt("摘要內容")
    assert '"mentions"' in result
    assert "摘要內容" in result


def test_build_m1_prompt_includes_scoring_schema():
    result = prompts.build_m1_prompt("摘要內容")
    assert "signal_direction" in result
    assert "摘要內容" in result


def test_build_newsletter_summary_prompt_includes_title_and_body():
    result = prompts.build_newsletter_summary_prompt("文章內容", "電子報標題")
    assert "電子報標題" in result
    assert "文章內容" in result


def test_build_card_points_prompt_includes_sections_text():
    result = prompts.build_card_points_prompt("## 核心觀點\n內容")
    assert "## 核心觀點\n內容" in result
    assert "[HOOK]" in result


def test_build_newsletter_card_points_prompt_includes_ticker_rules():
    result = prompts.build_newsletter_card_points_prompt("## 提及標的\n內容")
    assert "提及標的章節專屬規則" in result


def test_build_card_points_shorts_prompt_includes_sections_text():
    result = prompts.build_card_points_shorts_prompt("## 核心觀點\n內容")
    assert "Shorts" in result
    assert "## 核心觀點\n內容" in result


def test_build_newsletter_card_points_shorts_prompt_includes_sections_text():
    result = prompts.build_newsletter_card_points_shorts_prompt("## 提及標的\n內容")
    assert "Shorts" in result
    assert "## 提及標的\n內容" in result


def test_build_earnings_analysis_prompt_includes_ticker_and_table():
    data = {
        "charts": {
            "revenue": {"labels": ["2026Q1"], "values_m": [1000], "yoy_pct": [10]},
            "eps": {"values": [1.2], "yoy_pct": [5]},
            "margins": {"gross": [40], "operating": [20], "net": [15]},
            "fcf": {"values_m": [300]},
        }
    }
    result = prompts.build_earnings_analysis_prompt("AAPL", "Apple Inc.", data, "USD")
    assert "AAPL" in result
    assert "Apple Inc." in result
    assert "2026Q1" in result
