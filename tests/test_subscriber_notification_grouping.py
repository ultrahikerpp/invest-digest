"""Each subscriber must receive ONE email per approve batch, containing only
the episodes from channels they subscribed to (previously: one email per episode)."""
import runner
from backend import subscriber as sub


def _results():
    return [
        {"channel_id": "UC_A", "channel_name": "A", "title": "A1", "video_id": "a1", "summary_path": None},
        {"channel_id": "UC_B", "channel_name": "B", "title": "B1", "video_id": "b1", "summary_path": None},
        {"channel_id": "UC_A", "channel_name": "A", "title": "A2", "video_id": "a2", "summary_path": None},
        {"channel_id": "UC_C", "channel_name": "C", "title": "C1", "video_id": "c1", "summary_path": None},
    ]


def test_one_email_per_subscriber_with_only_subscribed_channels(monkeypatch):
    subs_by_channel = {
        "UC_A": [{"email": "both@x.com", "unsubscribe_token": "t1"},
                 {"email": "a@x.com", "unsubscribe_token": "t2"}],
        "UC_B": [{"email": "both@x.com", "unsubscribe_token": "t1"}],
        "UC_C": [],
    }
    query_calls = []

    def fake_get(channel_id):
        query_calls.append(channel_id)
        return subs_by_channel[channel_id]

    sent = []
    monkeypatch.setattr(sub, "get_confirmed_subscribers", fake_get)
    monkeypatch.setattr(
        sub, "send_episodes_notification",
        lambda email, token, eps: sent.append((email, token, [e["video_id"] for e in eps])),
    )

    runner._send_subscriber_notifications(_results())

    assert sorted(sent) == [
        ("a@x.com", "t2", ["a1", "a2"]),
        ("both@x.com", "t1", ["a1", "b1", "a2"]),
    ]
    assert sorted(query_calls) == ["UC_A", "UC_B", "UC_C"], "query each channel once"


def test_subject_episode_count_matches_episodes_not_channels(monkeypatch):
    captured = []
    monkeypatch.setattr("backend.worker.send_html_email",
                        lambda subject, html, to: captured.append((subject, html)))
    eps = [
        {"channel_name": "JC", "title": "J1", "video_id": "j1", "summary_excerpt": ""},
        {"channel_name": "JC", "title": "J2", "video_id": "j2", "summary_excerpt": ""},
        {"channel_name": "Gooaye", "title": "G1", "video_id": "g1", "summary_excerpt": ""},
        {"channel_name": "FOMO", "title": "F1", "video_id": "f1", "summary_excerpt": "",
         "source_type": "newsletter"},
    ]
    sub.send_episodes_notification("u@x.com", "tok", eps)

    subject, html = captured[0]
    assert "共 4 集" in subject  # 4 episodes, though only 3 channels
    assert html.count("#/episode/") == len(eps)


def test_episodes_notification_groups_by_channel_in_single_email(monkeypatch):
    captured = []
    monkeypatch.setattr("backend.worker.send_html_email",
                        lambda subject, html, to: captured.append((subject, html, to)))
    eps = [
        {"channel_name": "A", "title": "A1", "video_id": "a1", "summary_excerpt": "x"},
        {"channel_name": "B", "title": "B<1>", "video_id": "b1", "summary_excerpt": "y",
         "source_type": "newsletter"},
    ]
    sub.send_episodes_notification("u@x.com", "tok", eps)

    assert len(captured) == 1
    subject, html, to = captured[0]
    assert to == "u@x.com"
    assert "2 集" in subject
    assert "#/episode/a1" in html and "#/episode/b1" in html
    assert "B&lt;1&gt;" in html
    assert "unsubscribe?token=tok" in html
