import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.browser_common import clean_json_raw, clean_ui_artifacts, parse_hook_sections


def test_clean_json_raw_strips_code_fence():
    raw = '```json\n{"a": 1}\n```'
    assert clean_json_raw(raw) == '{"a": 1}'


def test_clean_json_raw_strips_single_backtick_wrap():
    raw = '`{"a": 1}`'
    assert clean_json_raw(raw) == '{"a": 1}'


def test_clean_json_raw_extracts_object_from_surrounding_text():
    raw = 'Here is the JSON:\n{"a": 1}\nHope that helps!'
    assert clean_json_raw(raw) == '{"a": 1}'


def test_parse_hook_sections_extracts_hook_and_sections():
    raw = (
        "[HOOK]\n"
        "驚人數字曝光？\n\n"
        "[核心觀點]\n"
        "重點一\n"
        "重點二\n"
        "重點三\n"
    )
    points, hook = parse_hook_sections(raw, max_points=5)
    assert hook == "驚人數字曝光？"
    assert points == {"核心觀點": ["重點一", "重點二", "重點三"]}


def test_clean_ui_artifacts_strips_leading_widget_chrome():
    # Reproduces the noise captured in docs/data/earnings/AAPL.json
    raw = (
        "以下是 Apple Inc. 的財報圖表視覺化，搭配完整 Markdown 分析：\n\n\n"
        "  ::view-transition-group(*),\n"
        "  ::view-transition-old(*),\n"
        "  ::view-transition-new(*) {\n"
        "    animation-duration: 0.25s;\n"
        "    animation-timing-function: cubic-bezier(0.19, 1, 0.22, 1);\n"
        "  }\nV\n\nvisualizeV\n\nvisualize show_widget\n---\n\n\n### 季度趨勢解讀\n\n本季營收成長。"
    )
    cleaned = clean_ui_artifacts(raw)
    assert cleaned == (
        "以下是 Apple Inc. 的財報圖表視覺化，搭配完整 Markdown 分析：\n\n---\n\n### 季度趨勢解讀\n\n本季營收成長。"
    )
    assert "view-transition" not in cleaned
    assert "show_widget" not in cleaned


def test_clean_ui_artifacts_drops_widget_marker_fused_with_text():
    # Reproduces docs/data/earnings/MSFT.json, where "show_widget" runs
    # directly into the next sentence with no separating newline.
    raw = (
        "::view-transition-group(*) {\n  animation-duration: 0.25s;\n}\n"
        "V\n\nvisualizeV\n\nvisualize show_widget以下為完整 Markdown 分析：\n\n\n\n---\n\n### 季度趨勢解讀"
    )
    cleaned = clean_ui_artifacts(raw)
    assert "show_widget" not in cleaned
    assert cleaned.startswith("---")


def test_parse_hook_sections_truncates_to_max_points():
    raw = (
        "[章節]\n"
        "1. 一\n"
        "2. 二\n"
        "3. 三\n"
        "4. 四\n"
        "5. 五\n"
        "6. 六\n"
    )
    points, hook = parse_hook_sections(raw, max_points=4)
    assert points["章節"] == ["一", "二", "三", "四"]
    assert hook == ""
