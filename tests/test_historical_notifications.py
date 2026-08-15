import runner


def test_reprocess_approves_historical_batch_without_notifications(monkeypatch, tmp_path):
    transcript_path = tmp_path / "v1.txt"
    transcript_path.write_text("transcript", encoding="utf-8")
    existing_summary = tmp_path / "old.md"
    existing_summary.write_text(
        "---\nchannel_name: Gooaye 股癌\n---\n\n### 核心觀點\nold\n",
        encoding="utf-8",
    )
    new_summary = tmp_path / "new.md"

    class Connection:
        def execute(self, *args):
            return self

        def commit(self):
            pass

        def close(self):
            pass

    episode = {
        "video_id": "v1",
        "title": "EP1",
        "channel_id": "UC_GOOAYE",
        "transcript_path": str(transcript_path),
        "summary_path": str(existing_summary),
        "published_at": "2026-01-01",
    }

    class Worker:
        @staticmethod
        def generate_summary(*args, **kwargs):
            return "### 投資心法\nnew\n"

    approve_args = {}

    monkeypatch.setattr(runner, "_ensure_dirs", lambda: None)
    monkeypatch.setattr(runner, "_load_channels", lambda: [])
    monkeypatch.setattr(runner, "_import_worker", lambda: Worker)
    monkeypatch.setattr(runner, "_get_db", lambda: Connection())
    monkeypatch.setattr(runner, "_select_episodes", lambda *args, **kwargs: [episode])
    monkeypatch.setattr(runner, "_get_channel_style", lambda *args: "gooaye_notes")
    monkeypatch.setattr(runner, "_get_channel_name", lambda *args: "Gooaye 股癌")
    monkeypatch.setattr(runner, "_get_channel_host", lambda *args: None)
    monkeypatch.setattr(runner, "_summary_path", lambda *args: new_summary)
    monkeypatch.setattr(
        runner,
        "cmd_approve",
        lambda **kwargs: approve_args.update(kwargs),
    )

    runner.cmd_reprocess(provider="chatgpt", channel_id="UC_GOOAYE", limit=1)

    assert approve_args == {
        "provider": "chatgpt",
        "channel_id": "UC_GOOAYE",
        "min_episode": None,
        "max_episode": None,
        "send_notifications": False,
    }


def test_approve_can_skip_completion_and_subscriber_notifications(monkeypatch, tmp_path):
    summary_path = tmp_path / "summary.md"
    summary_path.write_text(
        "---\ntitle: EP1\nchannel_name: Gooaye 股癌\n---\n\n# EP1\n",
        encoding="utf-8",
    )

    class Connection:
        def close(self):
            pass

    email_calls = []
    subscriber_calls = []

    class Worker:
        GMAIL_USER = "owner@example.com"

        @staticmethod
        def generate_hashtags(*args, **kwargs):
            return "#tag"

        @staticmethod
        def send_notification_email(*args, **kwargs):
            email_calls.append((args, kwargs))

    episode = {
        "video_id": "v1",
        "title": "EP1",
        "channel_id": "UC_GOOAYE",
        "summary_path": str(summary_path),
    }

    monkeypatch.setattr(runner, "_ensure_dirs", lambda: None)
    monkeypatch.setattr(runner, "_import_worker", lambda: Worker)
    monkeypatch.setattr(runner, "_get_db", lambda: Connection())
    monkeypatch.setattr(runner, "_select_episodes", lambda *args, **kwargs: [episode])
    monkeypatch.setattr(runner, "_update_frontmatter_hashtags", lambda *args: None)
    monkeypatch.setattr(runner, "cmd_shorts_cards", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_sync_to_wiki", lambda *args: None)
    monkeypatch.setattr(runner, "_sync_to_research_data", lambda *args: None)
    monkeypatch.setattr(runner, "_mark_done", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "_send_subscriber_notifications",
        lambda *args, **kwargs: subscriber_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(runner, "BASE_DIR", tmp_path)

    runner.cmd_approve(
        provider="chatgpt",
        channel_id="UC_GOOAYE",
        send_notifications=False,
    )

    assert email_calls == []
    assert subscriber_calls == []
