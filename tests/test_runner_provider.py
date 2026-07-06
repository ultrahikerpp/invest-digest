import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from runner import _extract_provider, _strip_provider


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
