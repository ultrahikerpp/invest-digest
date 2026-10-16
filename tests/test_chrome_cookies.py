"""Regression tests: cookies must come from the Chrome profile of CHROME_PROFILE_EMAIL,
not whichever profile browser_cookie3 finds first (`Default`)."""
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import chatgpt_browser, chrome_cookies, claude_browser


def _make_chrome_dir(tmp_path: Path) -> Path:
    profiles = {
        "Default": "other@gmail.com",
        "Profile 3": "yocoppp@gmail.com",
    }
    for name in profiles:
        (tmp_path / name).mkdir()
        (tmp_path / name / "Cookies").write_bytes(b"")
    local_state = {"profile": {"info_cache": {
        name: {"user_name": email} for name, email in profiles.items()
    }}}
    (tmp_path / "Local State").write_text(json.dumps(local_state), encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake_cookie3(monkeypatch, tmp_path):
    chrome_dir = _make_chrome_dir(tmp_path)
    monkeypatch.setattr(chrome_cookies, "CHROME_USER_DATA_DIR", chrome_dir)
    monkeypatch.setenv("CHROME_PROFILE_EMAIL", "yocoppp@gmail.com")
    calls = []

    def chrome(cookie_file=None, domain_name=""):
        calls.append(cookie_file)
        return [types.SimpleNamespace(
            name="sessionKey", value="v", domain=domain_name, path="/", secure=True,
        )]

    monkeypatch.setitem(sys.modules, "browser_cookie3", types.SimpleNamespace(chrome=chrome))
    return chrome_dir, calls


def test_claude_cookies_read_from_configured_profile(fake_cookie3):
    chrome_dir, calls = fake_cookie3
    claude_browser._get_claude_cookies()
    assert calls and all(c == str(chrome_dir / "Profile 3" / "Cookies") for c in calls)


def test_chatgpt_cookies_read_from_configured_profile(fake_cookie3):
    chrome_dir, calls = fake_cookie3
    chatgpt_browser._get_chatgpt_cookies()
    assert calls and all(c == str(chrome_dir / "Profile 3" / "Cookies") for c in calls)


def test_resolve_cookie_file_is_case_insensitive(tmp_path):
    chrome_dir = _make_chrome_dir(tmp_path)
    assert chrome_cookies.resolve_cookie_file("YOCOPPP@gmail.com", chrome_dir) == str(
        chrome_dir / "Profile 3" / "Cookies"
    )


def test_resolve_cookie_file_unknown_email_lists_known_accounts(tmp_path):
    chrome_dir = _make_chrome_dir(tmp_path)
    with pytest.raises(RuntimeError, match="other@gmail.com"):
        chrome_cookies.resolve_cookie_file("nobody@gmail.com", chrome_dir)


def test_unset_email_falls_back_to_browser_cookie3_default(fake_cookie3, monkeypatch):
    _, calls = fake_cookie3
    monkeypatch.setenv("CHROME_PROFILE_EMAIL", "")
    chrome_cookies.load_chrome_cookies("claude.ai")
    assert calls == [None]
