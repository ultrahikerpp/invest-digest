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
