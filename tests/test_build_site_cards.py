import build_site
from pathlib import Path


def test_sync_card_directory_preserves_legacy_urls_and_refreshes_cta(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "card_02_cta.png").write_bytes(b"new amber CTA")
    (destination / "card_07_cta.png").write_bytes(b"old purple CTA")
    (destination / "card_08.png").write_bytes(b"old section")

    build_site._sync_card_directory(source, destination)

    assert sorted(path.name for path in destination.glob("card_*.png")) == [
        "card_02_cta.png",
        "card_07_cta.png",
        "card_08.png",
    ]
    assert (destination / "card_07_cta.png").read_bytes() == b"new amber CTA"


def test_site_refreshes_episode_index_after_card_layout_changes():
    html = (Path(__file__).parent.parent / "docs" / "index.html").read_text(encoding="utf-8")

    assert "data/episodes.json?v=" in html
    assert "cache: 'no-store'" in html
