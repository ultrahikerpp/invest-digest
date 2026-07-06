import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.browser_common import clean_json_raw, parse_hook_sections


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
