import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from runner import (
    _extract_episode_bounds,
    _extract_provider,
    _strip_episode_bounds,
    _strip_provider,
    _extract_limit,
    _strip_limit,
)


def test_extract_provider_defaults_to_claude_when_absent():
    assert _extract_provider(["cards", "VID123"]) == "claude"


def test_extract_provider_finds_chatgpt_anywhere_in_list():
    assert _extract_provider(["cards", "--provider", "chatgpt", "VID123"]) == "chatgpt"
    assert _extract_provider(["cards", "VID123", "--provider", "chatgpt"]) == "chatgpt"


def test_extract_provider_exits_on_unknown_value():
    with pytest.raises(SystemExit) as exc_info:
        _extract_provider(["cards", "--provider", "gemini", "VID123"])
    assert exc_info.value.code != 0


def test_extract_provider_exits_when_provider_flag_is_last_token_with_no_value():
    # Finding 2: a trailing --provider with no value must error, not silently
    # fall back to "claude".
    with pytest.raises(SystemExit) as exc_info:
        _extract_provider(["cards", "VID123", "--provider"])
    assert exc_info.value.code != 0


def test_strip_provider_removes_flag_and_value_preserving_order():
    assert _strip_provider(["cards", "--provider", "chatgpt", "VID123"]) == ["cards", "VID123"]
    assert _strip_provider(["cards", "VID123", "--provider", "chatgpt"]) == ["cards", "VID123"]


def test_strip_provider_returns_list_unchanged_when_absent():
    args = ["cards", "VID123"]
    assert _strip_provider(args) == args


def test_extract_limit_defaults_to_none_when_absent():
    assert _extract_limit(["reprocess", "--channel", "abc"]) is None


def test_extract_limit_finds_value_anywhere_in_list():
    assert _extract_limit(["reprocess", "--limit", "3", "--channel", "abc"]) == 3
    assert _extract_limit(["reprocess", "--channel", "abc", "--limit", "3"]) == 3


def test_extract_limit_exits_on_non_integer_value():
    with pytest.raises(SystemExit) as exc_info:
        _extract_limit(["reprocess", "--limit", "abc"])
    assert exc_info.value.code != 0


def test_extract_limit_exits_on_zero_or_negative_value():
    with pytest.raises(SystemExit) as exc_info:
        _extract_limit(["reprocess", "--limit", "0"])
    assert exc_info.value.code != 0


def test_extract_limit_exits_when_flag_is_last_token_with_no_value():
    with pytest.raises(SystemExit) as exc_info:
        _extract_limit(["reprocess", "--limit"])
    assert exc_info.value.code != 0


def test_strip_limit_removes_flag_and_value_preserving_order():
    assert _strip_limit(["reprocess", "--limit", "3", "--channel", "abc"]) == ["reprocess", "--channel", "abc"]


def test_strip_limit_returns_list_unchanged_when_absent():
    args = ["reprocess", "--channel", "abc"]
    assert _strip_limit(args) == args


def test_extract_episode_bounds_finds_inclusive_range():
    assert _extract_episode_bounds(
        ["reprocess", "--min-episode", "634", "--max-episode", "679"]
    ) == (634, 679)


def test_extract_episode_bounds_rejects_reversed_range():
    with pytest.raises(SystemExit) as exc_info:
        _extract_episode_bounds(
            ["reprocess", "--min-episode", "679", "--max-episode", "634"]
        )
    assert exc_info.value.code != 0


def test_strip_episode_bounds_removes_flags_and_values():
    assert _strip_episode_bounds(
        ["reprocess", "--channel", "abc", "--min-episode", "634", "--max-episode", "679"]
    ) == ["reprocess", "--channel", "abc"]
