import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import runner


def test_cmd_weekly_uses_extended_timeout(tmp_path, monkeypatch):
    """cmd_weekly bundles a week's worth of summaries (routinely 30-40K+ chars)
    into one prompt; extended thinking alone can take 4+ minutes at that size
    (same threshold as the gooaye_notes path), so it must not fall back to the
    180s default used for small prompts.
    """
    summaries_dir = tmp_path / "summaries" / "chan"
    summaries_dir.mkdir(parents=True)
    episode = summaries_dir / "ep1.md"
    episode.write_text(
        "---\n"
        f"title: Test Episode\n"
        f"channel_name: Test Channel\n"
        f"published: {datetime.now().strftime('%Y-%m-%d')}\n"
        "---\n\n"
        "body text\n",
        encoding="utf-8",
    )

    weekly_dir = tmp_path / "weekly"
    monkeypatch.setattr(runner, "SUMMARIES_DIR", summaries_dir.parent)
    monkeypatch.setattr(runner, "WEEKLY_DIR", weekly_dir)

    captured = {}

    def fake_chat(prompt, provider="claude", timeout_secs=180):
        captured["timeout_secs"] = timeout_secs
        return "digest text"

    monkeypatch.setattr("backend.ai_provider.chat", fake_chat)

    runner.cmd_weekly(provider="claude")

    assert captured["timeout_secs"] >= 600
