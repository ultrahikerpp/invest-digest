#!/usr/bin/env python3
"""
Investment Digest Local Runner
Usage:
  python3 runner.py run                    # fetch all channels → transcribe → summarize → email review notice
  python3 runner.py run --channel <id>     # single channel
  python3 runner.py approve                # process all pending_review episodes: hashtags + cards + video + email
  python3 runner.py retry <video_id>       # retry failed summary for a single episode
  python3 runner.py build                  # regenerate static site
  python3 runner.py cards <video_id>       # generate PNG cards
  python3 runner.py video <video_id>       # generate MP4 from cards
  python3 runner.py notify                 # generate video for latest episode per channel + email
  python3 runner.py deploy                 # build + push to GitHub Pages
  python3 runner.py shorts-cards <video_id> # generate Shorts 9:16 cards (hook + sections + CTA)
  python3 runner.py shorts-video <video_id> # assemble Shorts MP4 from Shorts cards
  python3 runner.py setup-browser           # one-time Claude login setup for browser automation
  python3 runner.py renormalize            # apply entity_aliases.json to all existing mentions in the DB
  python3 runner.py fix-dates              # fix relative published_at dates (e.g. '1 天前') in the DB
  python3 runner.py score <video_id>       # M1 (Claude) + M4 (rule) DQS scoring for one episode
  python3 runner.py score <video_id> --m4-only  # M4 only, skip Claude
  python3 runner.py score --all            # M4 only for all episodes
  python3 runner.py score --all --force    # M1 + M4 for all episodes
  python3 runner.py weekly                 # synthesize cross-channel weekly digest from past 7 days

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
CARDS_SHORTS_DIR = BASE_DIR / "data" / "cards_shorts"
VIDEOS_SHORTS_DIR = BASE_DIR / "data" / "videos_shorts"

# ── Setup ─────────────────────────────────────────────────

def _ensure_dirs():
    for d in [SUMMARIES_DIR, TRANSCRIPTS_DIR, CARDS_DIR, VIDEOS_DIR,
              CARDS_SHORTS_DIR, VIDEOS_SHORTS_DIR]:
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
    # Migrate: add status column if it does not yet exist
    try:
        conn.execute("ALTER TABLE episodes ADD COLUMN status TEXT DEFAULT 'pending_review'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    # Data fix: existing processed rows should be 'done', not 'pending_review'
    conn.execute("UPDATE episodes SET status='done' WHERE processed=1 AND status='pending_review'")
    conn.commit()

    # Init analysis tables (mentions + episode_industries)
    from backend.analyzer import init_tables as _init_analysis_tables
    _init_analysis_tables(conn)

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


def _mark_pending_review(conn, channel_id: str, video: dict, transcript_path: str, summary_path: str):
    conn.execute("""
        INSERT OR IGNORE INTO episodes
        (channel_id, video_id, title, published_at, transcript_path, summary_path, processed, status)
        VALUES (?,?,?,?,?,?,0,'pending_review')
    """, (
        channel_id, video["video_id"], video["title"],
        video.get("published_at", ""), transcript_path, summary_path
    ))
    conn.commit()


def _mark_done(conn, video_id: str):
    conn.execute(
        "UPDATE episodes SET status='done', processed=1 WHERE video_id=?",
        (video_id,)
    )
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
            t_path = _transcript_path(v["video_id"], cname)
            t_path.write_text(transcript, encoding="utf-8")

            # Generate summary
            print(f"  Generating summary...")
            summary_body = worker.generate_summary(transcript, v["title"])

            # Build frontmatter without hashtags (added later in approve step)
            now = datetime.now().strftime("%Y-%m-%d")
            frontmatter = (
                f"---\n"
                f"title: {v['title']}\n"
                f"video_id: {v['video_id']}\n"
                f"channel_id: {cid}\n"
                f"channel_name: {cname}\n"
                f"published: {v.get('published_at', '')[:10]}\n"
                f"processed: {now}\n"
                f"---\n\n"
                f"# {v['title']}\n\n"
                f"🔗 [YouTube 觀看原片](https://youtube.com/watch?v={v['video_id']})\n\n"
            )
            full_md = frontmatter + summary_body

            s_path = _summary_path(v["video_id"], cname)
            s_path.write_text(full_md, encoding="utf-8")

            # Extract structured analysis (mentions + industries)
            print(f"  萃取標的與產業分析...")
            try:
                from backend.claude_browser import extract_analysis
                from backend.analyzer import save_mentions, save_industries
                analysis = extract_analysis(summary_body)
                save_mentions(conn, v["video_id"], cid, analysis["mentions"])
                save_industries(conn, v["video_id"], cid, analysis["industries"])
                if analysis["industries"]:
                    _update_frontmatter_field(s_path, "industries", ", ".join(analysis["industries"]))
                    print(f"  ✓ 產業：{', '.join(analysis['industries'])}")
                if analysis["mentions"]:
                    print(f"  ✓ 標的：{', '.join(m['name'] for m in analysis['mentions'][:5])}")
            except Exception as e:
                print(f"  ⚠️ 分析萃取失敗（不影響主流程）：{e}")

            _mark_pending_review(conn, cid, v, str(t_path), str(s_path))
            new_count += 1
            print(f"  ✓ 摘要已儲存：{v['title'][:50]}")

            # Send review notification email
            subject = f"[待審閱] {cname}｜{v['title']}"
            body = (
                f"新集數摘要已產出，請審閱後執行以下指令：\n\n"
                f"python3 runner.py approve\n\n"
                f"─────────────────────────\n"
                f"頻道：{cname}\n"
                f"標題：{v['title']}\n"
                f"YouTube：https://youtube.com/watch?v={v['video_id']}\n"
                f"摘要檔案：{s_path}\n"
                f"─────────────────────────\n\n"
                f"{summary_body}"
            )
            print(f"  寄送審閱通知郵件...")
            try:
                worker.send_notification_email(subject, body)
                print(f"  ✓ 郵件已寄至 {worker.GMAIL_USER}")
            except Exception as e:
                print(f"  ❌ 郵件發送失敗：{e}")

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
    summary_path = _find_summary_path(video_id)
    if summary_path is None:
        print(f"ERROR: Summary not found for {video_id}", file=sys.stderr)
        sys.exit(1)

    # Read channel_name and hashtags from frontmatter
    content = summary_path.read_text(encoding="utf-8")
    channel_name = ""
    hashtags = ""
    if content.startswith("---"):
        fm_end = content.find("---", 3)
        if fm_end != -1:
            fm = content[3:fm_end]
            for line in fm.splitlines():
                if line.startswith("channel_name:"):
                    channel_name = line.split(":", 1)[1].strip()
                elif line.startswith("channel_id:"):
                    cid = line.split(":", 1)[1].strip()
                    if not channel_name:
                        channel_name = _get_channel_name(cid, channels)
                elif line.startswith("hashtags:"):
                    hashtags = line.split(":", 1)[1].strip()

    output_dir = _cards_output_dir(video_id, channel_name or "unknown")

    from backend.card_generator import generate_cards
    card_paths = generate_cards(summary_path, channel_name, output_dir, hashtags=hashtags)
    print(f"Generated {len(card_paths)} cards in {output_dir}")
    for p in card_paths:
        print(f"  {p}")


# ── Video command ─────────────────────────────────────────

def _transcript_path(video_id: str, channel_name: str) -> Path:
    """Return the path for a transcript, organized by channel name."""
    d = TRANSCRIPTS_DIR / channel_name
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{video_id}.txt"


def _summary_path(video_id: str, channel_name: str) -> Path:
    """Return the path for a summary, organized by channel name."""
    d = SUMMARIES_DIR / channel_name
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{video_id}.md"


def _find_summary_path(video_id: str) -> Path | None:
    """Find a summary file by video_id, searching channel subdirectories."""
    for p in SUMMARIES_DIR.glob(f"*/{video_id}.md"):
        return p
    flat = SUMMARIES_DIR / f"{video_id}.md"
    return flat if flat.exists() else None


def _cards_output_dir(video_id: str, channel_name: str) -> Path:
    """Return the cards directory for a video, organized by channel name."""
    d = CARDS_DIR / channel_name / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _video_output_path(video_id: str, channel_name: str) -> Path:
    """Return the output path for a video, organized by channel name."""
    channel_dir = VIDEOS_DIR / channel_name
    channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir / f"{video_id}.mp4"


def cmd_video(video_id: str):
    _ensure_dirs()

    # Read channel_name from summary frontmatter first (needed for both paths)
    summary_path = _find_summary_path(video_id)
    channel_name = _parse_summary_meta(summary_path).get("channel_name", "unknown") if summary_path else "unknown"

    cards_dir = CARDS_DIR / channel_name / video_id
    if not cards_dir.exists():
        print(f"ERROR: Cards not found. Run: python3 runner.py cards {video_id}", file=sys.stderr)
        sys.exit(1)

    card_paths = sorted(cards_dir.glob("*.png"))
    if not card_paths:
        print(f"ERROR: No PNG cards in {cards_dir}", file=sys.stderr)
        sys.exit(1)

    output_path = _video_output_path(video_id, channel_name)

    from backend.video_maker import make_video
    make_video(card_paths, output_path, seconds_per_card=10)
    print(f"Video saved: {output_path}")


# ── Shorts commands ───────────────────────────────────────

def _shorts_cards_output_dir(video_id: str, channel_name: str) -> Path:
    d = CARDS_SHORTS_DIR / channel_name / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _shorts_video_output_path(video_id: str, channel_name: str) -> Path:
    channel_dir = VIDEOS_SHORTS_DIR / channel_name
    channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir / f"{video_id}_shorts.mp4"


def cmd_shorts_cards(video_id: str):
    """Generate Shorts-optimised 1080x1920 cards (hook + sections + CTA)."""
    _ensure_dirs()
    channels = _load_channels()
    summary_path = _find_summary_path(video_id)
    if summary_path is None:
        print(f"ERROR: Summary not found for {video_id}", file=sys.stderr)
        sys.exit(1)

    meta = _parse_summary_meta(summary_path)
    channel_name = meta.get("channel_name", "")
    if not channel_name:
        cid = meta.get("channel_id", "")
        channel_name = _get_channel_name(cid, channels)

    hashtags = meta.get("hashtags", "")
    output_dir = _shorts_cards_output_dir(video_id, channel_name)

    from backend.card_generator_shorts import generate_cards_shorts
    card_paths = generate_cards_shorts(summary_path, channel_name, output_dir, hashtags)
    print(f"Generated {len(card_paths)} Shorts cards in {output_dir}")
    for p in card_paths:
        print(f"  {p}")


def cmd_shorts_video(video_id: str):
    """Assemble Shorts MP4 (~56 seconds) from Shorts cards."""
    _ensure_dirs()

    summary_path = _find_summary_path(video_id)
    channel_name = _parse_summary_meta(summary_path).get("channel_name", "unknown") if summary_path else "unknown"

    cards_dir = CARDS_SHORTS_DIR / channel_name / video_id
    if not cards_dir.exists():
        print(f"ERROR: Shorts cards not found. Run: python3 runner.py shorts-cards {video_id}", file=sys.stderr)
        sys.exit(1)

    card_paths = sorted(cards_dir.glob("*.png"))
    if not card_paths:
        print(f"ERROR: No PNG cards in {cards_dir}", file=sys.stderr)
        sys.exit(1)

    output_path = _shorts_video_output_path(video_id, channel_name)

    from backend.video_maker import make_video
    # Hook and CTA cards: 5 seconds each; section cards: 7 seconds each.
    # Build per-card duration list and assemble via individual concat entries.
    durations = []
    for p in card_paths:
        name = p.stem
        if name.endswith("_hook") or name.endswith("_cta"):
            durations.append(5)
        else:
            durations.append(7)

    _make_video_variable_duration(card_paths, durations, output_path)
    print(f"Shorts video saved: {output_path}")


def _make_video_variable_duration(card_paths: list, durations: list[int], output_path: Path) -> Path:
    """
    Like video_maker.make_video but with per-card duration control.
    Falls back to uniform 7s if durations list doesn't match card count.
    """
    import subprocess, tempfile
    if len(durations) != len(card_paths):
        durations = [7] * len(card_paths)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for card, dur in zip(card_paths, durations):
            f.write(f"file '{Path(card).resolve()}'\n")
            f.write(f"duration {dur}\n")
        f.write(f"file '{Path(card_paths[-1]).resolve()}'\n")
        concat_file = Path(f.name)

    total_seconds = sum(durations)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-t", str(total_seconds),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0a0e1a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-800:]}")
    finally:
        concat_file.unlink(missing_ok=True)

    return output_path


# ── Frontmatter helpers ───────────────────────────────────

def _update_frontmatter_field(md_path: Path, field: str, value: str):
    """Insert or update a single field in a summary's YAML frontmatter."""
    content = md_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return
    end = content.find("---", 3)
    if end == -1:
        return

    fm_block = content[3:end]
    rest = content[end + 3:]

    lines = fm_block.splitlines(keepends=True)
    new_lines = []
    inserted = False
    for line in lines:
        if line.startswith(f"{field}:"):
            new_lines.append(f"{field}: {value}\n")
            inserted = True
        else:
            new_lines.append(line)
            if line.startswith("processed:") and not inserted:
                new_lines.append(f"{field}: {value}\n")
                inserted = True

    if not inserted:
        new_lines.append(f"{field}: {value}\n")

    md_path.write_text("---" + "".join(new_lines) + "---" + rest, encoding="utf-8")


def _update_frontmatter_hashtags(md_path: Path, hashtags: str):
    """Insert or update the hashtags field in a summary's YAML frontmatter."""
    content = md_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return
    end = content.find("---", 3)
    if end == -1:
        return

    fm_block = content[3:end]          # frontmatter content (without --- delimiters)
    rest = content[end + 3:]            # everything after closing ---

    lines = fm_block.splitlines(keepends=True)
    new_lines = []
    inserted = False
    for line in lines:
        if line.startswith("hashtags:"):
            new_lines.append(f"hashtags: {hashtags}\n")
            inserted = True
        else:
            new_lines.append(line)
            if line.startswith("processed:") and not inserted:
                new_lines.append(f"hashtags: {hashtags}\n")
                inserted = True

    if not inserted:
        new_lines.append(f"hashtags: {hashtags}\n")

    new_content = "---" + "".join(new_lines) + "---" + rest
    md_path.write_text(new_content, encoding="utf-8")


# ── Retry command ─────────────────────────────────────────

def cmd_retry(video_id: str):
    """Retry summary generation for a single failed episode."""
    _ensure_dirs()
    channels = _load_channels()
    worker = _import_worker()
    conn = _get_db()

    # Look up existing DB record
    ep = conn.execute("SELECT * FROM episodes WHERE video_id=?", (video_id,)).fetchone()

    if ep:
        channel_id = ep["channel_id"]
        title = ep["title"] or video_id
        channel_name = _get_channel_name(channel_id, channels)
        published_at = ep["published_at"] or ""
        print(f"找到記錄：{title[:60]}")

        # Remove old summary file if exists
        summary_path = (Path(ep["summary_path"]) if ep["summary_path"] else None) or _find_summary_path(video_id)
        if summary_path and summary_path.exists():
            summary_path.unlink()
            print(f"  已刪除舊摘要：{summary_path.name}")

        # Remove DB entry so we can re-insert cleanly
        conn.execute("DELETE FROM episodes WHERE video_id=?", (video_id,))
        conn.commit()
        print(f"  已清除資料庫記錄")
    else:
        print(f"資料庫中找不到 {video_id}，將嘗試直接下載並產製摘要")
        channel_id = None
        channel_name = "unknown"
        title = video_id
        published_at = ""

    # Re-use existing transcript if available, otherwise re-download
    t_path = _find_transcript_path(video_id)
    if t_path and t_path.exists():
        print(f"  使用已存在的逐字稿：{t_path}")
        transcript = t_path.read_text(encoding="utf-8")
    else:
        print(f"  下載並轉錄音訊...")
        transcript = worker.get_youtube_transcript(video_id)
        if not transcript:
            print(f"❌ 無法取得逐字稿，請確認 video_id 是否正確")
            conn.close()
            return
        # Save transcript (need channel_name for path)
        t_path = _transcript_path(video_id, channel_name)
        t_path.write_text(transcript, encoding="utf-8")
        print(f"  ✓ 逐字稿已儲存")

    # Generate summary
    print(f"  產生摘要（透過 Claude 瀏覽器）...")
    summary_body = worker.generate_summary(transcript, title)

    now = datetime.now().strftime("%Y-%m-%d")
    frontmatter = (
        f"---\n"
        f"title: {title}\n"
        f"video_id: {video_id}\n"
        f"channel_id: {channel_id or ''}\n"
        f"channel_name: {channel_name}\n"
        f"published: {published_at}\n"
        f"processed: {now}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"🔗 [YouTube 觀看原片](https://youtube.com/watch?v={video_id})\n\n"
    )
    full_md = frontmatter + summary_body

    s_path = _summary_path(video_id, channel_name)
    s_path.write_text(full_md, encoding="utf-8")

    # Re-insert as pending_review
    video_dict = {"video_id": video_id, "title": title, "published_at": published_at}
    _mark_pending_review(conn, channel_id or "", video_dict, str(t_path), str(s_path))

    conn.close()
    print(f"  ✓ 摘要已儲存：{s_path}")
    print(f"\n完成！執行以下指令審閱並發布：")
    print(f"  python3 runner.py approve")


# ── Reprocess command ─────────────────────────────────────

def _find_transcript_path(video_id: str) -> Path | None:
    """Find a transcript file by video_id, searching channel subdirectories."""
    for p in TRANSCRIPTS_DIR.glob(f"*/{video_id}.txt"):
        return p
    flat = TRANSCRIPTS_DIR / f"{video_id}.txt"
    return flat if flat.exists() else None


def cmd_reprocess():
    """Re-generate summaries for all episodes using the current prompt, then approve all."""
    _ensure_dirs()
    channels = _load_channels()
    worker = _import_worker()
    conn = _get_db()

    episodes = conn.execute("SELECT * FROM episodes").fetchall()
    if not episodes:
        print("資料庫中沒有集數")
        conn.close()
        return

    print(f"找到 {len(episodes)} 集，依序重新產製摘要（使用最新 Prompt）...\n")

    regenerated = 0
    for ep in episodes:
        video_id = ep["video_id"]
        title = ep["title"] or video_id
        channel_id = ep["channel_id"]

        # Locate transcript
        t_path = (Path(ep["transcript_path"]) if ep["transcript_path"] else None)
        if t_path is None or not t_path.exists():
            t_path = _find_transcript_path(video_id)
        if t_path is None or not t_path.exists():
            print(f"  ❌ 找不到逐字稿，略過：{title[:50]}")
            continue

        print(f"=== {title[:60]} ===")

        transcript = t_path.read_text(encoding="utf-8")

        # Preserve existing frontmatter fields
        existing_path = (Path(ep["summary_path"]) if ep["summary_path"] else None) or _find_summary_path(video_id)
        meta = _parse_summary_meta(existing_path) if existing_path and existing_path.exists() else {}
        channel_name = meta.get("channel_name", "") or _get_channel_name(channel_id, channels)
        published = meta.get("published", ep["published_at"] or "")
        processed = meta.get("processed", datetime.now().strftime("%Y-%m-%d"))

        # Re-generate summary with new prompt
        print(f"  重新產製摘要...")
        summary_body = worker.generate_summary(transcript, title)

        frontmatter = (
            f"---\n"
            f"title: {title}\n"
            f"video_id: {video_id}\n"
            f"channel_id: {channel_id}\n"
            f"channel_name: {channel_name}\n"
            f"published: {published}\n"
            f"processed: {processed}\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"🔗 [YouTube 觀看原片](https://youtube.com/watch?v={video_id})\n\n"
        )
        full_md = frontmatter + summary_body

        s_path = _summary_path(video_id, channel_name)
        s_path.write_text(full_md, encoding="utf-8")

        # Reset status so approve will pick it up
        conn.execute(
            "UPDATE episodes SET status='pending_review', processed=0, summary_path=? WHERE video_id=?",
            (str(s_path), video_id),
        )
        conn.commit()
        print(f"  ✓ 摘要已更新，重置為 pending_review\n")
        regenerated += 1

    conn.close()
    print(f"共重新產製 {regenerated} 集摘要\n")

    if regenerated == 0:
        return

    print("開始執行 approve（產出 hashtags、字卡、影片、部署）...\n")
    cmd_approve()


# ── Approve command ────────────────────────────────────────

def cmd_approve():
    """Process all pending_review episodes: generate hashtags, Shorts cards, Shorts video, then email summary."""
    _ensure_dirs()
    worker = _import_worker()
    conn = _get_db()

    pending = conn.execute(
        "SELECT * FROM episodes WHERE status='pending_review'"
    ).fetchall()

    if not pending:
        print("沒有待審閱的集數")
        conn.close()
        return

    print(f"找到 {len(pending)} 集待審閱的集數")
    results = []

    for ep in pending:
        video_id = ep["video_id"]
        channel_id = ep["channel_id"]
        title = ep["title"] or video_id
        _db_path = Path(ep["summary_path"]) if ep["summary_path"] else None
        summary_path = (_db_path if _db_path and _db_path.exists() else None) or _find_summary_path(video_id)

        print(f"\n=== {title[:60]} ===")

        if summary_path is None or not summary_path.exists():
            print(f"  ❌ 找不到摘要檔案：{video_id}")
            continue

        # Read the (possibly user-edited) md and extract summary body
        content = summary_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            fm_end = content.find("---", 3)
            summary_body = content[fm_end + 3:].strip() if fm_end != -1 else content
        else:
            summary_body = content

        # Resolve channel name from frontmatter
        meta = _parse_summary_meta(summary_path)
        channel_name = meta.get("channel_name", channel_id)

        # Generate hashtags from (possibly edited) summary
        print(f"  產生 hashtags...")
        hashtags = worker.generate_hashtags(summary_body, channel_name)

        # Write hashtags back into frontmatter
        _update_frontmatter_hashtags(summary_path, hashtags)
        print(f"  ✓ Hashtags: {hashtags}")

        # Generate Shorts cards (1080x1920)
        print(f"  產生 Shorts 字卡...")
        try:
            cmd_shorts_cards(video_id)
        except SystemExit:
            print(f"  ❌ Shorts 字卡產生失敗")
            continue

        # Generate Shorts video
        print(f"  產生 Shorts 影片...")
        try:
            cmd_shorts_video(video_id)
        except SystemExit:
            print(f"  ❌ Shorts 影片產生失敗")
            continue

        _mark_done(conn, video_id)
        print(f"  ✓ 完成")
        results.append({
            "channel_name": channel_name,
            "title": title,
            "hashtags": hashtags,
            "video_id": video_id,
        })

    conn.close()

    if not results:
        print("\n沒有成功處理的集數")
        return

    # Send completion notification email
    n = len(results)
    subject = f"[完成] 共 {n} 集影片已產出"
    lines = [f"共 {n} 集影片已產出\n"]
    for r in results:
        video_path = _shorts_video_output_path(r["video_id"], r["channel_name"])
        lines.append(f"{r['channel_name']}｜{r['title']}｜{r['hashtags']}")
        lines.append(f"  Shorts 影片路徑：{video_path}\n")
    body = "\n".join(lines)

    print(f"\n寄送完成通知郵件...")
    try:
        worker.send_notification_email(subject, body)
        print(f"✓ 郵件已寄至 {worker.GMAIL_USER}")
    except Exception as e:
        print(f"❌ 郵件發送失敗：{e}")

    print(f"\n共完成 {n} 集")

    # Auto-deploy: build static site + git commit + push
    deploy_script = BASE_DIR / "deploy.sh"
    if deploy_script.exists():
        print("\n自動部署網站...")
        result = subprocess.run(["bash", str(deploy_script)], cwd=BASE_DIR)
        if result.returncode != 0:
            print("❌ 部署失敗，請手動執行 runner.py deploy")
    else:
        print("❌ 找不到 deploy.sh，請手動執行 runner.py deploy")


# ── Notify Latest command ─────────────────────────────────

def _parse_summary_meta(md_path: Path) -> dict:
    """Extract frontmatter fields from a summary markdown file."""
    content = md_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    meta = {}
    for line in content[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def cmd_notify_latest():
    """Generate video for latest episode per channel and send email notification."""
    _ensure_dirs()
    channels = _load_channels()
    worker = _import_worker()

    # Build episode list with metadata
    episodes = []
    for md_path in SUMMARIES_DIR.glob("**/*.md"):
        meta = _parse_summary_meta(md_path)
        if not meta.get("channel_id"):
            continue
        episodes.append({
            "video_id": meta.get("video_id", md_path.stem),
            "channel_id": meta.get("channel_id", ""),
            "channel_name": meta.get("channel_name", ""),
            "title": meta.get("title", md_path.stem),
            "published": meta.get("published", ""),
            "processed": meta.get("processed", ""),
            "hashtags": meta.get("hashtags", ""),
            "mtime": md_path.stat().st_mtime,
        })

    if not episodes:
        print("No summaries found.")
        return

    # Find latest episode per channel
    # Sort key: EP number (if title has EP###) > processed date > file mtime
    import re as _re

    def _ep_sort_key(ep: dict) -> tuple:
        m = _re.search(r'EP(\d+)', ep.get("title", ""), _re.IGNORECASE)
        ep_num = int(m.group(1)) if m else 0
        # Normalise published: keep only ISO-parseable dates (YYYY-MM-DD...)
        pub = ep.get("published", "")
        pub_norm = pub[:10] if len(pub) >= 10 and pub[0].isdigit() else ""
        return (ep_num, pub_norm, ep.get("processed", ""), ep.get("mtime", 0))

    latest: dict[str, dict] = {}
    for ep in episodes:
        cid = ep["channel_id"]
        if cid not in latest or _ep_sort_key(ep) > _ep_sort_key(latest[cid]):
            latest[cid] = ep

    for cid, ep in latest.items():
        vid = ep["video_id"]
        cname = ep["channel_name"] or _get_channel_name(cid, channels)
        print(f"\n=== {cname} — {ep['title'][:50]} ===")

        # Generate cards if missing
        cards_dir = CARDS_DIR / cname / vid
        card_paths = sorted(cards_dir.glob("*.png")) if cards_dir.exists() else []
        if not card_paths:
            print(f"  字卡不存在，先產生字卡...")
            summary_path = _find_summary_path(vid)
            if summary_path is None:
                print(f"  ❌ 找不到摘要：{vid}")
                continue
            cards_dir = _cards_output_dir(vid, cname)
            from backend.card_generator import generate_cards
            card_paths = generate_cards(summary_path, cname, cards_dir)
            print(f"  ✓ {len(card_paths)} 張字卡")

        # Generate video if missing
        video_path = _video_output_path(vid, cname)
        if not video_path.exists():
            print(f"  產生影片...")
            from backend.video_maker import make_video
            make_video(sorted(cards_dir.glob("*.png")), video_path, seconds_per_card=10)
            print(f"  ✓ 影片：{video_path}")
        else:
            print(f"  影片已存在：{video_path}")

        # Send email
        hashtags = ep["hashtags"]
        subject = f"{cname}｜{ep['title']}"
        body = f"影片已產出\n\n{hashtags}\n\n影片路徑：{video_path}"
        print(f"  寄送通知郵件...")
        try:
            worker.send_notification_email(subject, body)
            print(f"  ✓ 郵件已寄至 {worker.GMAIL_USER}")
        except Exception as e:
            print(f"  ❌ 郵件發送失敗：{e}")


# ── Backfill Analysis command ─────────────────────────────

def cmd_backfill_analysis():
    """Run extract_analysis on all historical summaries that haven't been analysed yet."""
    from backend.claude_browser import extract_analysis
    from backend.analyzer import has_analysis, save_mentions, save_industries

    conn = _get_db()
    episodes = conn.execute("SELECT * FROM episodes ORDER BY created_at ASC").fetchall()
    if not episodes:
        print("資料庫中沒有集數")
        conn.close()
        return

    pending = [ep for ep in episodes if not has_analysis(conn, ep["video_id"])]
    print(f"找到 {len(pending)} 集尚未分析（共 {len(episodes)} 集）")

    done = 0
    for ep in pending:
        video_id = ep["video_id"]
        title = ep["title"] or video_id
        channel_id = ep["channel_id"]

        summary_path = (Path(ep["summary_path"]) if ep["summary_path"] else None) or _find_summary_path(video_id)
        if summary_path is None or not summary_path.exists():
            print(f"  ❌ 找不到摘要，略過：{title[:50]}")
            continue

        content = summary_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            fm_end = content.find("---", 3)
            summary_body = content[fm_end + 3:].strip() if fm_end != -1 else content
        else:
            summary_body = content

        print(f"\n=== {title[:60]} ===")
        print(f"  萃取分析...")
        try:
            analysis = extract_analysis(summary_body)
            save_mentions(conn, video_id, channel_id, analysis["mentions"])
            save_industries(conn, video_id, channel_id, analysis["industries"])
            if analysis["industries"]:
                _update_frontmatter_field(summary_path, "industries", ", ".join(analysis["industries"]))
                print(f"  ✓ 產業：{', '.join(analysis['industries'])}")
            if analysis["mentions"]:
                print(f"  ✓ 標的：{', '.join(m['name'] for m in analysis['mentions'][:5])}")
            done += 1
        except Exception as e:
            print(f"  ❌ 失敗：{e}")

    conn.close()
    print(f"\n完成！共分析 {done}/{len(pending)} 集")


# ── Trending command ───────────────────────────────────────

def cmd_trending(days: int = 30):
    """Print top 10 most-mentioned entities in the last N days."""
    from backend.analyzer import get_trending_mentions, get_industry_stats

    conn = _get_db()
    trending = get_trending_mentions(conn, days)
    industries = get_industry_stats(conn, days)
    conn.close()

    print(f"\n📊 近 {days} 天熱門標的 Top 10")
    print(f"{'名稱':<15} {'代碼':<8} {'提及':<6} {'看多':<5} {'看空':<5} {'中立'}")
    print("-" * 55)
    for r in trending:
        ticker = r["ticker"] or "-"
        print(f"{r['name']:<15} {ticker:<8} {r['count']:<6} {r['bullish']:<5} {r['bearish']:<5} {r['neutral']}")

    if not trending:
        print("（暫無資料）")

    print(f"\n🏭 產業熱度（近 {days} 天）")
    for r in industries:
        bar = "█" * r["count"]
        print(f"  {r['name']:<10} {r['count']:>4}  {bar}")

    if not industries:
        print("（暫無資料）")


# ── Track command ──────────────────────────────────────────

def cmd_track(name: str):
    """Show all episodes that mention a specific entity."""
    from backend.analyzer import get_entity_track

    conn = _get_db()
    records = get_entity_track(conn, name)
    conn.close()

    if not records:
        print(f"找不到提及「{name}」的集數")
        return

    print(f"\n🔍 提及「{name}」的集數（共 {len(records)} 筆）\n")
    for r in records:
        sentiment_icon = {"看多": "▲", "看空": "▼", "中立": "→"}.get(r["sentiment"] or "", "?")
        ticker_str = f" ({r['ticker']})" if r["ticker"] else ""
        print(f"  {sentiment_icon} {r['entity_name']}{ticker_str}")
        print(f"     {r['title'] or r['video_id']}")
        print(f"     處理日：{r['processed_at']}  https://youtube.com/watch?v={r['video_id']}\n")


# ── Divergence command ────────────────────────────────────

def cmd_divergence(days: int = 90, min_channels: int = 2):
    """Print cross-channel sentiment divergence analysis."""
    from backend.analyzer import get_cross_channel_divergence

    channels = _load_channels()
    channel_names = {ch["channel_id"]: ch["name"] for ch in channels}

    conn = _get_db()
    entities = get_cross_channel_divergence(
        conn, days=days, min_channels=min_channels, channel_names=channel_names
    )
    conn.close()

    if not entities:
        print(f"近 {days} 天內沒有被 {min_channels}+ 頻道同時提及的標的")
        return

    diverged = [e for e in entities if e["consensus"] == "多空分歧"]
    consensus = [e for e in entities if e["consensus"] != "多空分歧"]

    print(f"\n🔀 多空觀點比較（近 {days} 天，{min_channels}+ 頻道）")
    print(f"共 {len(entities)} 個標的  ·  分歧 {len(diverged)} 個  ·  共識 {len(consensus)} 個\n")

    icons = {"看多": "▲", "看空": "▼", "中立": "→"}
    badge = {
        "多空分歧": "🔥 多空分歧",
        "看多共識": "✅ 看多共識",
        "看空共識": "❌ 看空共識",
        "中立共識": "➖ 中立共識",
        "偏多": "↗ 偏多",
        "偏空": "↘ 偏空",
    }

    for e in entities:
        ticker_str = f" ({e['ticker']})" if e["ticker"] else ""
        label = badge.get(e["consensus"], e["consensus"])
        print(f"{label}  {e['name']}{ticker_str}  —  {e['total_mentions']} 次提及")
        for ch in e["channels"]:
            icon = icons.get(ch["stance"], "?")
            print(f"  {icon}  {ch['channel_name']:<20} {ch['stance']}  ({ch['mentions']} 次)")
        print()


# ── Renormalize command ───────────────────────────────────

def cmd_renormalize():
    """Apply entity_aliases.json normalization to all existing mentions in the DB."""
    from backend.analyzer import _load_aliases, normalize_entity_name

    conn = _get_db()
    aliases = _load_aliases()
    if not aliases:
        print("entity_aliases.json 中沒有別名設定")
        conn.close()
        return

    rows = conn.execute("SELECT id, entity_name FROM mentions").fetchall()
    updated = 0
    for row in rows:
        canonical = aliases.get(row["entity_name"])
        if canonical and canonical != row["entity_name"]:
            conn.execute("UPDATE mentions SET entity_name=? WHERE id=?", (canonical, row["id"]))
            updated += 1
    conn.commit()
    conn.close()
    print(f"✓ 已正規化 {updated} 筆標的名稱（共 {len(rows)} 筆）")


# ── Fix Dates command ─────────────────────────────────────

def cmd_fix_dates():
    """Fix episodes where published_at is a relative string (e.g. '1 天前') by using created_at as fallback."""
    import re as _re
    conn = _get_db()
    rows = conn.execute("SELECT video_id, published_at, created_at FROM episodes").fetchall()

    fixed = 0
    for row in rows:
        pub = row["published_at"] or ""
        # A valid ISO date starts with 4 digits followed by a dash
        if pub and _re.match(r'^\d{4}-\d{2}-\d{2}', pub):
            continue  # already OK

        # Use created_at (which is always a proper timestamp) as a fallback date
        fallback = (row["created_at"] or "")[:10]
        if not fallback:
            continue

        conn.execute(
            "UPDATE episodes SET published_at=? WHERE video_id=?",
            (fallback, row["video_id"])
        )
        fixed += 1
        print(f"  Fixed {row['video_id']}: '{pub}' → '{fallback}'")

    conn.commit()
    conn.close()
    print(f"\n✓ 修正了 {fixed} 筆 published_at 日期")


# ── Score command ─────────────────────────────────────────

def _read_summary_body(md_path: Path) -> str:
    """Return the body of a summary (strip YAML frontmatter if present)."""
    content = md_path.read_text(encoding="utf-8")
    if content.startswith("---"):
        fm_end = content.find("---", 3)
        return content[fm_end + 3:].strip() if fm_end != -1 else content
    return content


def _score_episode(video_id: str, run_m1: bool = True) -> None:
    """Score a single episode with M1 (optional) and M4, display results."""
    from backend.dqs import score_m4

    summary_path = _find_summary_path(video_id)
    if summary_path is None:
        print(f"ERROR: 找不到 {video_id} 的摘要檔案", file=sys.stderr)
        return

    meta = _parse_summary_meta(summary_path)
    title = meta.get("title", video_id)
    summary_body = _read_summary_body(summary_path)

    # ── M4 (rule-based) ───────────────────────────────────
    from datetime import date as _date
    pub_str = meta.get("published", "")
    ref_date = None
    if pub_str and len(pub_str) >= 10:
        try:
            ref_date = _date.fromisoformat(pub_str[:10])
        except ValueError:
            pass

    m4_score, coverage = score_m4(summary_body, reference_date=ref_date)

    # ── M1 (Claude browser) ───────────────────────────────
    m1_score: float | None = None
    if run_m1:
        print(f"  [M1] 使用 Claude 評分訊號品質...")
        from backend.claude_browser import score_m1
        m1_score = score_m1(summary_body)

    # ── Display ───────────────────────────────────────────
    print(f"\n{'═'*55}")
    print(f"  {title[:50]}")
    print(f"  video_id: {video_id}")
    print(f"{'─'*55}")
    if m1_score is not None:
        status = f"{m1_score:.2f}" if m1_score >= 0 else "失敗 (-1)"
        print(f"  M1 訊號品質 (Claude):  {status}")
    print(f"  M4 覆蓋廣度 (規則):    {m4_score:.2f}")
    print(f"{'─'*55}")
    for cat, hit in coverage.items():
        icon = "✓" if hit else "✗"
        print(f"    {icon} {cat}")
    print(f"{'═'*55}\n")

    # ── Persist to frontmatter ────────────────────────────
    _update_frontmatter_field(summary_path, "dqs_m4", str(m4_score))
    if m1_score is not None and m1_score >= 0:
        _update_frontmatter_field(summary_path, "dqs_m1", str(m1_score))


def cmd_score(video_id: str | None = None, all_episodes: bool = False, run_m1: bool = True) -> None:
    """Score episodes with M1 (Claude) + M4 (rule-based) DQS metrics."""
    _ensure_dirs()

    if all_episodes:
        from backend.dqs import score_m4
        from datetime import date as _date

        md_paths = sorted(SUMMARIES_DIR.glob("**/*.md"))
        if not md_paths:
            print("找不到任何摘要檔案")
            return

        label = "M1 + M4" if run_m1 else "M4"
        print(f"找到 {len(md_paths)} 個摘要，執行 {label} 評分...\n")
        results = []
        for md_path in md_paths:
            meta = _parse_summary_meta(md_path)
            vid = meta.get("video_id", md_path.stem)
            title = meta.get("title", vid)
            summary_body = _read_summary_body(md_path)

            pub_str = meta.get("published", "")
            ref_date = None
            if pub_str and len(pub_str) >= 10:
                try:
                    ref_date = _date.fromisoformat(pub_str[:10])
                except ValueError:
                    pass

            m4_score, coverage = score_m4(summary_body, reference_date=ref_date)
            _update_frontmatter_field(md_path, "dqs_m4", str(m4_score))

            m1_score: float | None = None
            if run_m1:
                from backend.claude_browser import score_m1
                print(f"  [M1] {title[:40]}...")
                m1_score = score_m1(summary_body)
                if m1_score >= 0:
                    _update_frontmatter_field(md_path, "dqs_m1", str(m1_score))

            m1_str = f"  M1={m1_score:.2f}" if m1_score is not None and m1_score >= 0 else ""
            results.append((m4_score, title[:45]))
            print(f"  M4={m4_score:.2f}{m1_str}  {title[:50]}")

        avg = sum(r[0] for r in results) / len(results) if results else 0
        print(f"\n平均 M4 分數：{avg:.2f}（共 {len(results)} 集）")
        print(f"dqs_m4{' + dqs_m1' if run_m1 else ''} 欄位已寫入各摘要 frontmatter")

    elif video_id:
        _score_episode(video_id, run_m1=run_m1)

    else:
        print("Usage: runner.py score <video_id>  |  runner.py score --all", file=sys.stderr)
        sys.exit(1)


# ── Weekly command ────────────────────────────────────────

WEEKLY_DIR = BASE_DIR / "data" / "weekly"

def cmd_weekly():
    """Synthesize a cross-channel weekly digest from the past 7 days of summaries."""
    from datetime import timedelta
    import re

    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

    cutoff = datetime.now() - timedelta(days=7)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    # Collect summaries published in the past 7 days
    md_files = sorted(SUMMARIES_DIR.glob("*/*.md"))
    episodes_for_weekly = []
    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        # Parse frontmatter
        meta: dict = {}
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                fm_block = content[3:end]
                for line in fm_block.splitlines():
                    m = re.match(r'^(\w+):\s*(.*)', line)
                    if m:
                        meta[m.group(1)] = m.group(2).strip()
                body = content[end + 3:].lstrip("\n")
            else:
                body = content
        else:
            body = content

        published = meta.get("published", "")
        if not published or published < cutoff_str:
            continue

        title = meta.get("title", md_path.stem)
        channel_name = meta.get("channel_name", "")
        episodes_for_weekly.append((title, channel_name, body))

    if not episodes_for_weekly:
        print("No episodes published in the past 7 days. Nothing to synthesize.")
        return

    print(f"Found {len(episodes_for_weekly)} episode(s) from the past 7 days.")

    # Build summaries block: channel + title + first 800 chars of body
    summaries_parts = []
    for title, channel_name, body in episodes_for_weekly:
        snippet = body[:800].strip()
        header = f"【{channel_name}】{title}" if channel_name else title
        summaries_parts.append(f"### {header}\n\n{snippet}")
    summaries_block = "\n\n---\n\n".join(summaries_parts)

    prompt = f"""你是一位財經分析整合員。以下是本週各投資頻道的摘要集錦，請整合成一份跨頻道週報。

要求：
- 用繁體中文
- 找出各頻道本週的共同主題與分歧觀點
- 標出本週最多頻道關注的標的
- 指出各頻道觀點差異最大的地方
- 最後一段「本週共識」：寫出各頻道最大公約數觀點
- **重要**：提及任何觀點時，必須明確標注來源，格式為「頻道名稱《集數名稱》」，例如「股癌《EP637》認為…」或「游庭皓的財經皓角《2026/03/18 早晨速解讀》提到…」

## 格式

## 本週共同主題
## 各頻道重點摘要（每個頻道 2-3 句）
## 標的共識
## 觀點分歧
## 本週共識

---

{summaries_block}"""

    print("Synthesizing weekly digest via Claude...")
    from backend.claude_browser import chat as claude_chat
    result = claude_chat(prompt)

    # Strip page-UI artifacts that bleed into the extracted response.
    # Patterns seen: ::view-transition CSS, "V", "visualize", "show_widget"
    _ARTIFACT_PATTERNS = re.compile(
        r'::view-transition|animation-duration|animation-timing-function|'
        r'cubic-bezier|visualize|show_widget'
    )
    cleaned_lines = []
    for line in result.splitlines():
        stripped = line.strip()
        # Drop lines that are pure UI artifacts or a lone "V"
        if _ARTIFACT_PATTERNS.search(stripped):
            continue
        if stripped in ('V', '}'):
            continue
        cleaned_lines.append(line)
    result = '\n'.join(cleaned_lines)
    # Collapse runs of blank lines left by the cleanup
    result = re.sub(r'\n{3,}', '\n\n', result).strip()

    # Determine week label (ISO year-week)
    now = datetime.now()
    iso_year, iso_week, _ = now.isocalendar()
    week_label = f"{iso_year}-{iso_week:02d}"
    today_str = now.strftime("%Y-%m-%d")

    frontmatter = (
        f"---\n"
        f"week: {week_label}\n"
        f"generated: {today_str}\n"
        f"episodes: {len(episodes_for_weekly)}\n"
        f"---\n\n"
    )
    full_md = frontmatter + result

    out_path = WEEKLY_DIR / f"{week_label}.md"
    out_path.write_text(full_md, encoding="utf-8")
    print(f"✓ Weekly digest saved: {out_path}")


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

    elif cmd == "approve":
        cmd_approve()

    elif cmd == "retry":
        if len(args) < 2:
            print("Usage: runner.py retry <video_id>", file=sys.stderr)
            sys.exit(1)
        cmd_retry(args[1])

    elif cmd == "reprocess":
        cmd_reprocess()

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

    elif cmd == "shorts-cards":
        if len(args) < 2:
            print("Usage: runner.py shorts-cards <video_id>", file=sys.stderr)
            sys.exit(1)
        cmd_shorts_cards(args[1])

    elif cmd == "shorts-video":
        if len(args) < 2:
            print("Usage: runner.py shorts-video <video_id>", file=sys.stderr)
            sys.exit(1)
        cmd_shorts_video(args[1])

    elif cmd == "deploy":
        cmd_deploy()

    elif cmd == "notify":
        cmd_notify_latest()

    elif cmd == "setup-browser":
        from backend.claude_browser import setup_login
        setup_login()

    elif cmd == "backfill-analysis":
        cmd_backfill_analysis()

    elif cmd == "trending":
        days = 30
        if len(args) >= 3 and args[1] == "--days":
            try:
                days = int(args[2])
            except ValueError:
                pass
        cmd_trending(days)

    elif cmd == "track":
        if len(args) < 3 or args[1] != "--name":
            print("Usage: runner.py track --name <entity_name>", file=sys.stderr)
            sys.exit(1)
        cmd_track(args[2])

    elif cmd == "divergence":
        days = 90
        min_channels = 2
        i = 1
        while i < len(args):
            if args[i] == "--days" and i + 1 < len(args):
                days = int(args[i + 1]); i += 2
            elif args[i] == "--min-channels" and i + 1 < len(args):
                min_channels = int(args[i + 1]); i += 2
            else:
                i += 1
        cmd_divergence(days, min_channels)

    elif cmd == "renormalize":
        cmd_renormalize()

    elif cmd == "fix-dates":
        cmd_fix_dates()

    elif cmd == "score":
        flags = set(a for a in args[1:] if a.startswith("--"))
        positional = [a for a in args[1:] if not a.startswith("--")]
        m4_only = "--m4-only" in flags
        force_m1 = "--force" in flags
        run_m1 = force_m1 or (not m4_only)
        if "--all" in flags or (not positional):
            cmd_score(all_episodes=True, run_m1=run_m1)
        else:
            cmd_score(video_id=positional[0], run_m1=run_m1)

    elif cmd == "weekly":
        cmd_weekly()

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
