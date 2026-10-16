from pathlib import Path

from backend import worker


def test_download_audio_uses_ytdlp_best_audio(monkeypatch, tmp_path):
    calls = {}

    class FakeYDL:
        def __init__(self, options):
            calls["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            calls["url"] = url
            calls["download"] = download
            output = Path(calls["options"]["outtmpl"].replace("%(id)s", "video-1").replace("%(ext)s", "webm"))
            output.write_bytes(b"audio")
            return {"id": "video-1", "ext": "webm"}

        def prepare_filename(self, info):
            return calls["options"]["outtmpl"].replace("%(id)s", info["id"]).replace("%(ext)s", info["ext"])

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)

    result = worker._download_audio("video-1", tmp_path)

    assert result == tmp_path / "video-1.webm"
    assert calls["url"] == "https://www.youtube.com/watch?v=video-1"
    assert calls["download"] is True
    assert calls["options"]["format"] == "bestaudio/best"
    assert calls["options"]["noplaylist"] is True


def test_download_audio_avoids_broken_tv_downgraded_client(monkeypatch, tmp_path):
    """yt-dlp's default client cascade (which includes tv_downgraded) currently
    fails YouTube signature decryption ("The page needs to be reloaded.") or
    403s on download, see yt-dlp/yt-dlp#17389. We pin player_client to the
    android client, verified to extract and download cleanly."""
    calls = {}

    class FakeYDL:
        def __init__(self, options):
            calls["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            output = Path(calls["options"]["outtmpl"].replace("%(id)s", "video-1").replace("%(ext)s", "webm"))
            output.write_bytes(b"audio")
            return {"id": "video-1", "ext": "webm"}

        def prepare_filename(self, info):
            return calls["options"]["outtmpl"].replace("%(id)s", info["id"]).replace("%(ext)s", info["ext"])

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)

    worker._download_audio("video-1", tmp_path)

    player_clients = calls["options"]["extractor_args"]["youtube"]["player_client"]
    assert "tv_downgraded" not in player_clients
