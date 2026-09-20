"""Regression tests for claude_browser response-completion detection.

Bug: with claude.ai extended thinking, generation (thinking + streaming) can
outlast the Stop-button wait; the old stability check then returned whatever
was on screen — the thinking status label or a truncated partial answer —
which got saved as a corrupt summary.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from playwright.sync_api import Error as PWError

from backend import claude_browser


STATUS_LABEL = "整理逐字稿並架構化成投資產業筆記。整理逐字稿並架構化成投資產業筆記。"
FINAL_TEXT = "## 本集主題總覽\n\n完整筆記內容"


class FakePage:
    """Simulates claude.ai: generation stays active for `running_polls`
    completion probes (status label on screen), then finishes with FINAL_TEXT.
    """

    def __init__(self, running_polls: int):
        self.running_polls = running_polls
        self.probe_calls = 0

    def evaluate(self, script, *args):
        if "Stop response" in script:  # _generation_running probe
            self.probe_calls += 1
            return self.probe_calls <= self.running_polls
        # _extract_last_response
        if self.probe_calls <= self.running_polls:
            return STATUS_LABEL
        return FINAL_TEXT


def test_stable_response_waits_out_generation(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    page = FakePage(running_polls=5)
    result = claude_browser._wait_for_stable_response(page, timeout_secs=60)
    assert result == FINAL_TEXT


def test_stable_response_returns_empty_not_partial_on_timeout(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    class NeverFinishes(FakePage):
        def __init__(self):
            super().__init__(running_polls=10**9)

    result = claude_browser._wait_for_stable_response(NeverFinishes(), timeout_secs=0)
    assert result == ""


NAV_ERROR = "Page.evaluate: Execution context was destroyed, most likely because of a navigation"


class ReloadingPage(FakePage):
    """claude.ai hard-reloads once mid-poll: the first `fail_on` probe
    ("probe" = completion check, "extract" = text capture) raises Playwright's
    navigation error, as seen in the wild right after submit.
    """

    def __init__(self, fail_on: str, url: str, running_polls: int = 0):
        super().__init__(running_polls=running_polls)
        self.fail_on = fail_on
        self.url = url
        self.reloaded = False

    def wait_for_load_state(self, state):
        pass

    def evaluate(self, script, *args):
        is_probe = "Stop response" in script
        if not self.reloaded and is_probe == (self.fail_on == "probe"):
            self.reloaded = True
            raise PWError(NAV_ERROR)
        return super().evaluate(script, *args)


@pytest.mark.parametrize("fail_on", ["probe", "extract"])
def test_stable_response_survives_reload_inside_conversation(monkeypatch, fail_on):
    """A reload after the submit landed (URL is /chat/<id>) is harmless: keep polling."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    page = ReloadingPage(fail_on, url="https://claude.ai/chat/abc-123")
    result = claude_browser._wait_for_stable_response(page, timeout_secs=60)
    assert result == FINAL_TEXT


@pytest.mark.parametrize("url", ["https://claude.ai/new", "https://claude.ai/login"])
def test_stable_response_fails_fast_when_reload_drops_the_conversation(monkeypatch, url):
    """Reloaded outside a conversation = the prompt never landed; polling can't
    succeed, so fail with the URL instead of burning the whole timeout.
    """
    monkeypatch.setattr(time, "sleep", lambda s: None)
    page = ReloadingPage("probe", url=url)
    with pytest.raises(RuntimeError, match=url):
        claude_browser._wait_for_stable_response(page, timeout_secs=600)


def test_stable_response_does_not_swallow_other_playwright_errors(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    class Closed(FakePage):
        def evaluate(self, script, *args):
            raise PWError("Page.evaluate: Target page, context or browser has been closed")

    with pytest.raises(PWError, match="has been closed"):
        claude_browser._wait_for_stable_response(Closed(running_polls=0), timeout_secs=60)
