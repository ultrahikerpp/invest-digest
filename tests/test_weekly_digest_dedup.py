"""Regression coverage for when the weekly digest email gets sent.

Context: cmd_weekly() (synthesizes the cross-channel weekly article) used to
call cmd_weekly_digest() (sends the subscriber email) immediately, so
subscribers got emailed before the user had a chance to review the freshly
generated article. The send is now tied to cmd_deploy() instead — it fires
only once this ISO week's digest article file exists (i.e. after `weekly`
has run and the user has deployed), guarded by a per-ISO-week marker so
re-running `deploy` (or the unrelated Sunday cron) within the same week
never double-sends.
"""
import sqlite3
import sys
import types
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


def test_cmd_weekly_does_not_trigger_weekly_digest_send(tmp_path, monkeypatch):
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

    assert calls == [], "cmd_weekly must not send the email itself — that now waits for cmd_deploy()"


def test_cmd_deploy_sends_weekly_digest_when_article_exists(tmp_path, monkeypatch):
    weekly_dir = tmp_path / "weekly"
    weekly_dir.mkdir()
    iso_year, iso_week, _ = datetime.now().isocalendar()
    (weekly_dir / f"{iso_year}-{iso_week:02d}.md").write_text("digest", encoding="utf-8")

    monkeypatch.setattr(runner, "WEEKLY_DIR", weekly_dir)
    monkeypatch.setattr(runner, "cmd_build", lambda: None)
    monkeypatch.setattr(
        runner, "subprocess",
        types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(returncode=0)),
    )

    calls = []
    monkeypatch.setattr(runner, "cmd_weekly_digest", lambda: calls.append(True))

    try:
        runner.cmd_deploy()
    except SystemExit as e:
        assert e.code == 0

    assert calls == [True], "cmd_deploy must send once this week's reviewed digest article exists"


def test_cmd_deploy_skips_weekly_digest_when_no_article_this_week(tmp_path, monkeypatch):
    weekly_dir = tmp_path / "weekly"
    weekly_dir.mkdir()

    monkeypatch.setattr(runner, "WEEKLY_DIR", weekly_dir)
    monkeypatch.setattr(runner, "cmd_build", lambda: None)
    monkeypatch.setattr(
        runner, "subprocess",
        types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(returncode=0)),
    )

    calls = []
    monkeypatch.setattr(runner, "cmd_weekly_digest", lambda: calls.append(True))

    try:
        runner.cmd_deploy()
    except SystemExit as e:
        assert e.code == 0

    assert calls == [], "cmd_deploy must not send when `weekly` hasn't generated this week's article"


def test_cmd_deploy_skips_weekly_digest_when_deploy_script_fails(tmp_path, monkeypatch):
    weekly_dir = tmp_path / "weekly"
    weekly_dir.mkdir()
    iso_year, iso_week, _ = datetime.now().isocalendar()
    (weekly_dir / f"{iso_year}-{iso_week:02d}.md").write_text("digest", encoding="utf-8")

    monkeypatch.setattr(runner, "WEEKLY_DIR", weekly_dir)
    monkeypatch.setattr(runner, "cmd_build", lambda: None)
    monkeypatch.setattr(
        runner, "subprocess",
        types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(returncode=1)),
    )

    calls = []
    monkeypatch.setattr(runner, "cmd_weekly_digest", lambda: calls.append(True))

    try:
        runner.cmd_deploy()
    except SystemExit as e:
        assert e.code == 1

    assert calls == [], "cmd_deploy must not email subscribers when the deploy itself failed"


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
