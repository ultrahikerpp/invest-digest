"""Regression coverage for auto-sending the weekly digest email from cmd_weekly.

Context: cmd_weekly() (synthesizes the cross-channel weekly article) and
cmd_deploy() never called cmd_weekly_digest() (sends the subscriber email) —
they were fully decoupled, so subscribers only got emailed via a separate
Sunday 17:30 cron. cmd_weekly() now triggers the send itself, guarded by a
per-ISO-week marker so re-running `weekly` (or the unrelated Sunday cron)
within the same week never double-sends.
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import runner


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "subscriptions.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            video_id TEXT NOT NULL UNIQUE,
            title TEXT,
            published_at TEXT,
            transcript_path TEXT,
            summary_path TEXT,
            processed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending_review'
        )
        """
    )
    conn.execute(
        "INSERT INTO episodes (channel_id, video_id, title, published_at, summary_path, status) "
        "VALUES ('chan1', 'vid1', 'Test Episode', ?, '', 'done')",
        (datetime.now().strftime("%Y-%m-%d"),),
    )
    conn.commit()
    conn.close()
    return db_path


def test_cmd_weekly_triggers_weekly_digest_send(tmp_path, monkeypatch):
    summaries_dir = tmp_path / "summaries" / "chan"
    summaries_dir.mkdir(parents=True)
    (summaries_dir / "ep1.md").write_text(
        "---\ntitle: Test Episode\nchannel_name: Test Channel\n"
        f"published: {datetime.now().strftime('%Y-%m-%d')}\n---\n\nbody text\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(runner, "SUMMARIES_DIR", summaries_dir.parent)
    monkeypatch.setattr(runner, "WEEKLY_DIR", tmp_path / "weekly")
    monkeypatch.setattr("backend.ai_provider.chat", lambda prompt, provider="claude", timeout_secs=180: "digest text")

    calls = []
    monkeypatch.setattr(runner, "cmd_weekly_digest", lambda: calls.append(True))

    runner.cmd_weekly(provider="claude")

    assert calls == [True], "cmd_weekly must trigger cmd_weekly_digest() so subscribers get emailed"


def test_cmd_weekly_digest_marks_sent_and_skips_on_rerun(tmp_path, monkeypatch):
    from backend import subscriber as sub

    monkeypatch.setattr(runner, "DB_PATH", _make_db(tmp_path))
    monkeypatch.setattr(runner, "WEEKLY_DIR", tmp_path / "weekly")

    sent_calls = []
    monkeypatch.setattr(
        sub, "get_weekly_digest_subscribers",
        lambda: [{"email": "a@example.com", "unsubscribe_token": "tok"}],
    )
    monkeypatch.setattr(
        sub, "send_weekly_digest",
        lambda email, token, episodes, week_label: sent_calls.append(email),
    )

    runner.cmd_weekly_digest()
    assert sent_calls == ["a@example.com"], "first run this week must send"

    runner.cmd_weekly_digest()
    assert sent_calls == ["a@example.com"], "second run same week must be a no-op (no duplicate send)"


def test_cmd_weekly_digest_sends_again_in_a_new_week(tmp_path, monkeypatch):
    from backend import subscriber as sub

    monkeypatch.setattr(runner, "DB_PATH", _make_db(tmp_path))
    weekly_dir = tmp_path / "weekly"
    monkeypatch.setattr(runner, "WEEKLY_DIR", weekly_dir)

    sent_calls = []
    monkeypatch.setattr(
        sub, "get_weekly_digest_subscribers",
        lambda: [{"email": "a@example.com", "unsubscribe_token": "tok"}],
    )
    monkeypatch.setattr(
        sub, "send_weekly_digest",
        lambda email, token, episodes, week_label: sent_calls.append(email),
    )

    runner.cmd_weekly_digest()
    assert len(sent_calls) == 1

    # Simulate "a week later": drop last week's marker, matching what would
    # naturally happen once the ISO week rolls over.
    for marker in weekly_dir.glob(".digest_sent_*"):
        marker.unlink()

    runner.cmd_weekly_digest()
    assert len(sent_calls) == 2, "a new week must send even though a prior week's marker existed"
