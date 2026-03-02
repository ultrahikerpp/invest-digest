#!/usr/bin/env python3
"""
Investment Digest Local Runner
Usage:
  python3 runner.py run                    # fetch all channels → transcribe → summarize → email review notice
  python3 runner.py run --channel <id>     # single channel
  python3 runner.py approve                # process all pending_review episodes: hashtags + cards + video + email
  python3 runner.py build                  # regenerate static site
  python3 runner.py cards <video_id>       # generate PNG cards
  python3 runner.py video <video_id>       # generate MP4 from cards
  python3 runner.py notify                 # generate video for latest episode per channel + email
  python3 runner.py deploy                 # build + push to GitHub Pages
  python3 runner.py setup-browser          # one-time Claude login setup for browser automation

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
    # Migrate: add status column if it does not yet exist
    try:
        conn.execute("ALTER TABLE episodes ADD COLUMN status TEXT DEFAULT 'pending_review'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    # Data fix: existing processed rows should be 'done', not 'pending_review'
    conn.execute("UPDATE episodes SET status='done' WHERE processed=1 AND status='pending_review'")
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
                f"published: {v.get('published_at', '')}\n"
                f"processed: {now}\n"
                f"---\n\n"
                f"# {v['title']}\n\n"
                f"🔗 [YouTube 觀看原片](https://youtube.com/watch?v={v['video_id']})\n\n"
            )
            full_md = frontmatter + summary_body

            s_path = _summary_path(v["video_id"], cname)
            s_path.write_text(full_md, encoding="utf-8")

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

    output_dir = _cards_output_dir(video_id, channel_name or "unknown")

    from backend.card_generator import generate_cards
    card_paths = generate_cards(summary_path, channel_name, output_dir)
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


# ── Frontmatter helpers ───────────────────────────────────

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
    """Process all pending_review episodes: generate hashtags, cards, video, then email summary."""
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
        summary_path = (Path(ep["summary_path"]) if ep["summary_path"] else None) or _find_summary_path(video_id)

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

        # Generate cards
        print(f"  產生字卡...")
        try:
            cmd_cards(video_id)
        except SystemExit:
            print(f"  ❌ 字卡產生失敗")
            continue

        # Generate video
        print(f"  產生影片...")
        try:
            cmd_video(video_id)
        except SystemExit:
            print(f"  ❌ 影片產生失敗")
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
        video_path = _video_output_path(r["video_id"], r["channel_name"])
        lines.append(f"{r['channel_name']}｜{r['title']}｜{r['hashtags']}")
        lines.append(f"  影片路徑：{video_path}\n")
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

    elif cmd == "deploy":
        cmd_deploy()

    elif cmd == "notify":
        cmd_notify_latest()

    elif cmd == "setup-browser":
        from backend.claude_browser import setup_login
        setup_login()

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
