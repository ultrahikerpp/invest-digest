import runner


def test_no_deploy_flag_is_parsed_and_removed():
    args = ["reprocess", "--channel", "gooaye", "--no-deploy"]

    assert runner._extract_no_deploy(args) is True
    assert runner._strip_no_deploy(args) == ["reprocess", "--channel", "gooaye"]


def test_approve_no_deploy_skips_deployment(monkeypatch, tmp_path):
    summary_path = tmp_path / "summary.md"
    summary_path.write_text(
        "---\ntitle: EP1\nchannel_name: Gooaye 股癌\n---\n\n# EP1\n",
        encoding="utf-8",
    )

    class Connection:
        def close(self):
            pass

    class Worker:
        @staticmethod
        def generate_hashtags(*args, **kwargs):
            return "#tag"

    deployment_calls = []
    monkeypatch.setattr(runner, "_ensure_dirs", lambda: None)
    monkeypatch.setattr(runner, "_import_worker", lambda: Worker)
    monkeypatch.setattr(runner, "_get_db", lambda: Connection())
    monkeypatch.setattr(
        runner,
        "_select_episodes",
        lambda *args, **kwargs: [{
            "video_id": "v1",
            "title": "EP1",
            "channel_id": "UC_GOOAYE",
            "summary_path": str(summary_path),
        }],
    )
    monkeypatch.setattr(runner, "_update_frontmatter_hashtags", lambda *args: None)
    monkeypatch.setattr(runner, "cmd_shorts_cards", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_sync_to_wiki", lambda *args: None)
    monkeypatch.setattr(runner, "_sync_to_research_data", lambda *args: None)
    monkeypatch.setattr(runner, "_mark_done", lambda *args: None)
    monkeypatch.setattr(runner, "subprocess", type("Subprocess", (), {
        "run": staticmethod(lambda *args, **kwargs: deployment_calls.append(args)),
    }))
    monkeypatch.setattr(runner, "BASE_DIR", tmp_path)

    runner.cmd_approve(
        provider="chatgpt",
        channel_id="UC_GOOAYE",
        send_notifications=False,
        no_deploy=True,
    )

    assert deployment_calls == []
