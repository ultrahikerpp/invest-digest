import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.card_generator import _fallback_points, _truncate_at_boundary, parse_summary


def test_fallback_points_keeps_short_sentences_intact():
    # A 32-char sentence (typical for 投資觀念-style bullets) must not be
    # truncated — the old 25-char hard cutoff chopped it mid-sentence.
    content = "- 均值迴歸是不變的道理：需求仍在，但價格仍需要籌碼整理與估值回歸。"
    points = _fallback_points(content)
    assert points == ["均值迴歸是不變的道理：需求仍在，但價格仍需要籌碼整理與估值回歸。"]


def test_truncate_at_boundary_backs_off_instead_of_cutting_mid_word():
    # This is the exact string (and length) that produced the observed bug:
    # the old hard 25-char cutoff sliced inside "Alphabet（Google）",
    # rendering as "...Alphab et（Go…" once word-wrapped on the card.
    text = "美股／科技：Meta、蘋果、Alphabet（Google）、微軟、亞馬遜、輝達、特斯拉、博通、甲骨文"
    assert _truncate_at_boundary(text, 25) == "美股／科技：Meta、蘋果、…"


def test_fallback_points_skips_horizontal_rule_lines():
    content = "- 真實重點\n\n---\n"
    points = _fallback_points(content)
    assert points == ["真實重點"]


def test_parse_summary_excludes_trailing_disclaimer_block(tmp_path):
    # generate_summary() appends a "---\n**⚠️ 負責任 AI 聲明...**" disclaimer
    # with no heading of its own, so it used to get swallowed into the last
    # section's content and leak onto a card as a stray bullet (showing as
    # unrenderable tofu-box glyphs for the ⚠️ emoji).
    md = tmp_path / "summary.md"
    md.write_text(
        "---\n"
        "title: test\n"
        "---\n\n"
        "# 測試標題\n\n"
        "### 提及標的\n\n"
        "- 台積電（2330）\n\n"
        "---\n"
        "**⚠️ 負責任 AI 聲明與投資風險提示：**\n"
        "1. 本摘要由 AI 自動生成。\n",
        encoding="utf-8",
    )
    data = parse_summary(md)
    assert "⚠️" not in data["sections"]["提及標的"]
    assert "負責任 AI 聲明" not in data["sections"]["提及標的"]
    assert "台積電（2330）" in data["sections"]["提及標的"]
