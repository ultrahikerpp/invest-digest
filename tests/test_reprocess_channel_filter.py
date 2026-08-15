"""Tests for the channel filter used by reprocess/approve (--channel)."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runner import _select_episodes, _summary_matches_style


def test_summary_matches_style_detects_gooaye_sections():
    assert _summary_matches_style("...\n### 投資心法\n...", "gooaye_notes")
    assert _summary_matches_style("...\n## 投資心法\n...", "gooaye_notes")
    assert not _summary_matches_style("...\n### 核心觀點\n...", "gooaye_notes")
    # no style configured → never treated as already-restyled
    assert not _summary_matches_style("### 投資心法", None)
    assert not _summary_matches_style("", "gooaye_notes")


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE episodes (video_id TEXT, channel_id TEXT, status TEXT)"
    )
    rows = [
        ("v1", "UC_GOOAYE", "done"),
        ("v2", "UC_GOOAYE", "done"),
        ("v3", "UC_JC", "pending_review"),
        ("v4", "UC_JC", "done"),
    ]
    conn.executemany("INSERT INTO episodes VALUES (?, ?, ?)", rows)
    return conn


def test_select_all_episodes_without_filters():
    conn = _make_db()
    assert len(_select_episodes(conn)) == 4


def test_select_episodes_filters_by_channel():
    conn = _make_db()
    eps = _select_episodes(conn, channel_id="UC_GOOAYE")
    assert [e["video_id"] for e in eps] == ["v1", "v2"]


def test_select_episodes_filters_by_status_and_channel():
    conn = _make_db()
    # approve scoped to GOOAYE must NOT pick up the JC pending episode
    assert _select_episodes(conn, status="pending_review", channel_id="UC_GOOAYE") == []
    eps = _select_episodes(conn, status="pending_review")
    assert [e["video_id"] for e in eps] == ["v3"]


def test_select_episodes_filters_by_episode_number_range():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE episodes (video_id TEXT, channel_id TEXT, title TEXT, status TEXT)"
    )
    conn.executemany(
        "INSERT INTO episodes VALUES (?, ?, ?, ?)",
        [
            ("v633", "UC_GOOAYE", "EP633 | old", "done"),
            ("v634", "UC_GOOAYE", "EP634 | first", "done"),
            ("v679", "UC_GOOAYE", "EP679 | last", "done"),
            ("v680", "UC_GOOAYE", "EP680 | newer", "done"),
            ("v687", "UC_GOOAYE", "EP687 | newer", "pending_review"),
        ],
    )

    eps = _select_episodes(
        conn,
        channel_id="UC_GOOAYE",
        min_episode=634,
        max_episode=679,
    )

    assert [e["video_id"] for e in eps] == ["v679", "v634"]
