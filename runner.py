#!/usr/bin/env python3
"""
Investment Digest Local Runner
Usage:
  python3 runner.py run                    # fetch all channels → transcribe → summarize
  python3 runner.py run --channel <id>     # single channel
  python3 runner.py build                  # regenerate static site
  python3 runner.py cards <video_id>       # generate PNG cards
  python3 runner.py video <video_id>       # generate MP4 from cards
  python3 runner.py deploy                 # build + push to GitHub Pages

Crontab (daily at 8am):
  0 8 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py run >> data/runner.log 2>&1
"""

from __future__ import annotations

import sys
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
CHANNELS_FILE = BASE_DIR / "channels.json"
DB_PATH = BASE_DIR / "data" / "subscriptions.db"
SUMMARIES_DIR = BASE_DIR / "data" / "summaries"
TRANSCRIPTS_DIR = BASE_DIR / "data" / "transcripts"
CARDS_DIR = BASE_DIR / "data" / "cards"
VIDEOS_DIR = BASE_DIR / "data" / "videos"

# ── Setup ─────────────────────────────────────────────────

def _ensure_dirs():
    for d in [SUMMARIES_DIR, TRANSCRIPTS_DIR, CARDS_DIR, VIDEOS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _load_channels() -> list[dict]:
    if not CHANNELS_FILE.exists():
        print(f"ERROR: {CHANNELS_FILE} not found. Create it with channel config.", file=sys.stderr)
        sys.exit(1)
    with open(CHANNELS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    channels = data.get("channels", [])
    for ch in channels:
        for key in ("channel_id", "name"):
            if not ch.get(key):
                print(f"ERROR: channels.json entry missing required key: {key}", file=sys.stderr)
                sys.exit(1)
    return [ch for ch in channels if ch.get("active", True)]


def _get_channel_name(channel_id: str, channels: list[dict]) -> str:
    for ch in channels:
        if ch["channel_id"] == channel_id:
            return ch["name"]
    return channel_id


# ── Database ──────────────────────────────────────────────

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            video_id TEXT NOT NULL UNIQUE,
            title TEXT,
            published_at TEXT,
            transcript_path TEXT,
            summary_path TEXT,
            processed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def _is_processed(conn, video_id: str) -> bool:
    row = conn.execute("SELECT id FROM episodes WHERE video_id=?", (video_id,)).fetchone()
    return row is not None


def _mark_processed(conn, channel_id: str, video: dict, transcript_path: str, summary_path: str):
    conn.execute("""
        INSERT OR IGNORE INTO episodes
        (channel_id, video_id, title, published_at, transcript_path, summary_path, processed)
        VALUES (?,?,?,?,?,?,1)
    """, (
        channel_id, video["video_id"], video["title"],
        video.get("published_at", ""), transcript_path, summary_path
    ))
    conn.commit()


# ── Core worker functions (imported from backend/worker.py) ──

def _import_worker():
    """Lazy import to avoid loading Whisper on startup."""
    sys.path.insert(0, str(BASE_DIR))
    import backend.worker as w
    return w


# ── Run command ───────────────────────────────────────────

def cmd_run(channel_id: str | None = None):
    _ensure_dirs()
    channels = _load_channels()
    worker = _import_worker()

    targets = [ch for ch in channels if channel_id is None or ch["channel_id"] == channel_id]
    if not targets:
        print(f"ERROR: Channel {channel_id!r} not found in channels.json", file=sys.stderr)
        sys.exit(1)

    conn = _get_db()
    total_new = 0

    for ch in targets:
        cid = ch["channel_id"]
        cname = ch["name"]
        print(f"\n=== {cname} ({cid}) ===")

        videos = worker.get_latest_videos(cid)
        print(f"  Found {len(videos)} recent videos")

        new_count = 0
        for v in videos:
            if _is_processed(conn, v["video_id"]):
                print(f"  [skip] {v['title'][:60]}")
                continue

            print(f"  [new]  {v['title'][:60]}")

            # Download and transcribe
            transcript = worker.get_youtube_transcript(v["video_id"])
            if not transcript:
                print(f"  Skipping (no transcript)")
                continue

            # Save transcript
            t_path = TRANSCRIPTS_DIR / f"{v['video_id']}.txt"
            t_path.write_text(transcript, encoding="utf-8")

            # Generate summary
            print(f"  Generating summary...")
            summary_body = worker.generate_summary(transcript, v["title"])

            # Build frontmatter with channel_name
            now = datetime.now().strftime("%Y-%m-%d")
            frontmatter = (
                f"---\n"
                f"title: {v['title']}\n"
                f"video_id: {v['video_id']}\n"
                f"channel_id: {cid}\n"
                f"channel_name: {cname}\n"
                f"published: {v.get('published_at', '')}\n"
                f"processed: {now}\n"
                f"---\n\n"
                f"# {v['title']}\n\n"
                f"🔗 [YouTube 觀看原片](https://youtube.com/watch?v={v['video_id']})\n\n"
            )
            full_md = frontmatter + summary_body

            s_path = SUMMARIES_DIR / f"{v['video_id']}.md"
            s_path.write_text(full_md, encoding="utf-8")

            _mark_processed(conn, cid, v, str(t_path), str(s_path))
            new_count += 1
            print(f"  ✓ Done: {v['title'][:50]}")

        if new_count == 0:
            print(f"  No new videos")
        else:
            total_new += new_count

    conn.close()
    print(f"\nTotal new episodes processed: {total_new}")


# ── Build command ─────────────────────────────────────────

def cmd_build():
    print("Building static site...")
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "build_site.py")],
        cwd=BASE_DIR
    )
    sys.exit(result.returncode)


# ── Cards command ─────────────────────────────────────────

def cmd_cards(video_id: str):
    _ensure_dirs()
    channels = _load_channels()
    summary_path = SUMMARIES_DIR / f"{video_id}.md"
    if not summary_path.exists():
        print(f"ERROR: Summary not found: {summary_path}", file=sys.stderr)
        sys.exit(1)

    # Read channel_name from frontmatter
    content = summary_path.read_text(encoding="utf-8")
    channel_name = ""
    if content.startswith("---"):
        fm_end = content.find("---", 3)
        if fm_end != -1:
            fm = content[3:fm_end]
            for line in fm.splitlines():
                if line.startswith("channel_name:"):
                    channel_name = line.split(":", 1)[1].strip()
                    break
                if line.startswith("channel_id:"):
                    cid = line.split(":", 1)[1].strip()
                    channel_name = _get_channel_name(cid, channels)

    output_dir = CARDS_DIR / video_id
    output_dir.mkdir(parents=True, exist_ok=True)

    from backend.card_generator import generate_cards
    card_paths = generate_cards(str(summary_path), channel_name, str(output_dir))
    print(f"Generated {len(card_paths)} cards in {output_dir}")
    for p in card_paths:
        print(f"  {p}")


# ── Video command ─────────────────────────────────────────

def cmd_video(video_id: str):
    _ensure_dirs()
    cards_dir = CARDS_DIR / video_id
    if not cards_dir.exists():
        print(f"ERROR: Cards not found. Run: python3 runner.py cards {video_id}", file=sys.stderr)
        sys.exit(1)

    card_paths = sorted(cards_dir.glob("*.png"))
    if not card_paths:
        print(f"ERROR: No PNG cards in {cards_dir}", file=sys.stderr)
        sys.exit(1)

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = VIDEOS_DIR / f"{video_id}.mp4"

    from backend.video_maker import make_video
    make_video([str(p) for p in card_paths], str(output_path))
    print(f"Video saved: {output_path}")


# ── Deploy command ────────────────────────────────────────

def cmd_deploy():
    cmd_build()  # build first (exits on error)
    deploy_script = BASE_DIR / "deploy.sh"
    if not deploy_script.exists():
        print(f"ERROR: deploy.sh not found", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(["bash", str(deploy_script)], cwd=BASE_DIR)
    sys.exit(result.returncode)


# ── Entry point ───────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "run":
        channel_id = None
        if len(args) >= 3 and args[1] == "--channel":
            channel_id = args[2]
        cmd_run(channel_id)

    elif cmd == "build":
        cmd_build()

    elif cmd == "cards":
        if len(args) < 2:
            print("Usage: runner.py cards <video_id>", file=sys.stderr)
            sys.exit(1)
        cmd_cards(args[1])

    elif cmd == "video":
        if len(args) < 2:
            print("Usage: runner.py video <video_id>", file=sys.stderr)
            sys.exit(1)
        cmd_video(args[1])

    elif cmd == "deploy":
        cmd_deploy()

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
