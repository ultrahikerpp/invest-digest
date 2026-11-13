import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import card_generator, card_generator_shorts
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


def test_shorts_cards_use_same_amber_palette_as_square_cards():
    # card_generator_shorts.py (used by `approve`/`cards`/`shorts-cards`) kept its own
    # old indigo/purple/pink palette after the amber-terminal rebrand only touched
    # card_generator.py — Shorts cards rendered purple while square cards went amber.
    for attr in ("C_VIBE1", "C_VIBE2", "C_VIBE3", "C_BG", "C_BG2"):
        assert getattr(card_generator_shorts, attr) == getattr(card_generator, attr), attr


def test_shorts_generation_removes_stale_cards_from_previous_layout(monkeypatch, tmp_path):
    md = tmp_path / "summary.md"
    md.write_text(
        "---\ntitle: EP1\n---\n\n"
        "## 本集主題總覽\n\n- 新版重點\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "cards"
    output_dir.mkdir()
    (output_dir / "card_07_cta.png").write_bytes(b"old purple CTA")
    (output_dir / "card_08.png").write_bytes(b"old section")

    monkeypatch.setattr(
        "backend.ai_provider.generate_card_points_shorts",
        lambda sections, provider="claude": ({"本集主題總覽": ["新版重點"]}, "新版 Hook"),
    )

    cards = card_generator_shorts.generate_cards_shorts(
        md, "Gooaye 股癌", output_dir, "#投資", provider="chatgpt"
    )

    assert [p.name for p in cards] == [
        "card_00_hook.png",
        "card_01.png",
        "card_02_cta.png",
    ]
    assert not (output_dir / "card_07_cta.png").exists()
    assert not (output_dir / "card_08.png").exists()


# ── Markdown tables (codex-cli renders 提及標的 as a table) ──

TABLE = """| 類別 | 逐字稿明確提及 |
|---|---|
| 股票／公司 | Netflix、SoftBank、Palantir |
| ETF／投資方式 | 0050、指數投資 |
| 金融商品／指標 | 權證、VIX |"""


def test_fallback_points_turns_table_rows_into_cell_pairs():
    # Regression: a failed AI call fell back to raw "|---|---|" and "| a | b |" rows on the card.
    assert _fallback_points(TABLE) == [
        "股票／公司：Netflix、SoftBank、Palantir",
        "ETF／投資方式：0050、指數投資",
        "金融商品／指標：權證、VIX",
    ]


def test_fallback_points_handles_alignment_markers_and_missing_outer_pipes():
    content = "類別 | 內容\n:--- | ---:\n產業 | 記憶體、衛星\n| 市場 | 台股 |"
    assert _fallback_points(content) == ["產業：記憶體、衛星", "市場：台股"]


def test_fallback_points_table_without_header_separator_keeps_all_rows():
    # No separator row => it's not a header, every row is data.
    assert _fallback_points("| 產業 | 記憶體 |\n| 市場 | 台股 |") == ["產業：記憶體", "市場：台股"]


def test_fallback_points_table_rows_still_truncate_at_boundary():
    row = "| 產業 | " + "、".join(["半導體設備"] * 12) + " |"
    (point,) = _fallback_points(row)
    # cut lands right after a "、" list boundary, never mid-token
    assert point.startswith("產業：半導體設備、") and point.endswith("、…")
    assert len(point) <= card_generator._FALLBACK_MAX_CHARS + 1


def test_fallback_points_non_table_lines_with_a_pipe_are_unchanged():
    assert _fallback_points("- 看多 | 看空 並存的盤") == ["看多 | 看空 並存的盤"]


# ── boundaries found in review ────────────────────────────

def test_fallback_points_bullet_with_pipe_right_after_table_is_not_a_row():
    content = "| a | b |\n|---|---|\n| x | y |\n- 看多 | 看空"
    assert _fallback_points(content) == ["x：y", "看多 | 看空"]


def test_fallback_points_table_cells_drop_markers_and_unescape_pipes():
    content = "| k | v |\n|---|---|\n| - x | # y |\n| 1 \\| 2 | **z** |"
    assert _fallback_points(content) == ["x：y", "1 | 2：z"]


def test_fallback_points_three_plus_columns_use_first_cell_as_key():
    content = "| 標的 | 看法 | 題材 |\n|---|---|---|\n| 台積電 | 看多 | 先進製程 |"
    assert _fallback_points(content) == ["台積電：看多、先進製程"]


def test_fallback_points_single_column_table_keeps_data_rows():
    assert _fallback_points("| 重點 |\n|---|\n| 降息 |\n| 縮表 |") == ["降息", "縮表"]


def test_fallback_points_loose_dash_line_is_not_a_table_delimiter():
    # "- | -" has no 3-dash cells, so the line above it is plain text, not a dropped header.
    points = _fallback_points("A | B\n- | -")
    assert points[0] == "A | B" and len(points) == 2


def test_fallback_points_keeps_prose_around_a_table():
    content = "前言段落\n\n| k | v |\n|---|---|\n| 產業 | 記憶體 |\n\n- 結語重點"
    assert _fallback_points(content) == ["前言段落", "產業：記憶體", "結語重點"]
