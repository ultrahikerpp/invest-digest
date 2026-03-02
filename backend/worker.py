#!/usr/bin/env python3
from __future__ import annotations
"""
Worker: fetch new videos, download transcripts, generate summaries via Claude API
Usage:
  python3 worker.py fetch-all
  python3 worker.py fetch <channel_id>
  python3 worker.py summarize <video_id>
"""

import sys
import sqlite3
import json
import os
import re
import smtplib
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "subscriptions.db"
SUMMARIES_DIR = BASE_DIR / "data" / "summaries"
TRANSCRIPTS_DIR = BASE_DIR / "data" / "transcripts"

SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

def _load_dotenv():
    """Load KEY=VALUE pairs from .env into os.environ (does not override existing vars)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

_load_dotenv()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── YouTube Transcript (yt-dlp 下載音訊 + faster-whisper 轉文字) ──

_whisper_model = None

def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("  載入 Whisper 模型（首次執行需下載約 500MB）...")
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
        print("  Whisper 模型載入完成")
    return _whisper_model


def get_youtube_transcript(video_id: str) -> str | None:
    """下載音訊並用 faster-whisper 轉成文字。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 下載最佳音訊（使用 pytubefix）
        try:
            from pytubefix import YouTube
            yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
            stream = yt.streams.filter(only_audio=True).order_by("abr").last()
            if not stream:
                print(f"  找不到音訊串流 {video_id}")
                return None
            audio_path = stream.download(output_path=tmpdir, filename=video_id)
        except Exception as e:
            print(f"  音訊下載失敗 {video_id}: {e}")
            return None

        # 語音轉文字
        print(f"  轉文字中（需要數分鐘）...")
        try:
            model = _get_whisper_model()
            segments, _ = model.transcribe(
                audio_path,
                language="zh",
                beam_size=5,
                vad_filter=True,
            )
            lines = []
            for seg in segments:
                if not seg.text.strip():
                    continue
                mins, secs = divmod(int(seg.start), 60)
                hours, mins = divmod(mins, 60)
                ts = f"[{hours:02d}:{mins:02d}:{secs:02d}]" if hours else f"[{mins:02d}:{secs:02d}]"
                lines.append(f"{ts} {seg.text.strip()}")
            text = "\n".join(lines)
            return text if text else None
        except Exception as e:
            print(f"  轉文字失敗 {video_id}: {e}")
            return None

# ── Fetch new videos from channel ───────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

def _videos_from_rss(channel_id: str, max_results: int) -> list[dict]:
    """Try fetching videos via YouTube RSS feed."""
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(rss_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        content = resp.read().decode("utf-8")

    videos = []
    for entry in re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL)[:max_results]:
        vid   = re.search(r'<yt:videoId>(.*?)</yt:videoId>', entry)
        title = re.search(r'<title>(.*?)</title>', entry)
        pub   = re.search(r'<published>(.*?)</published>', entry)
        if vid and title:
            videos.append({
                "video_id":    vid.group(1),
                "title":       title.group(1),
                "published_at": pub.group(1) if pub else "",
            })
    return videos


def _videos_from_page(channel_id: str, max_results: int) -> list[dict]:
    """Fallback: scrape channel videos page via ytInitialData."""
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8")

    match = re.search(r'var ytInitialData = ({.*?});</script>', html, re.DOTALL)
    if not match:
        return []

    data = json.loads(match.group(1))
    videos = []
    try:
        tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
        for tab in tabs:
            tab_content = tab.get("tabRenderer", {}).get("content", {})
            items = (
                tab_content.get("richGridRenderer", {}).get("contents", [])
                or tab_content.get("sectionListRenderer", {})
                           .get("contents", [{}])[0]
                           .get("itemSectionRenderer", {})
                           .get("contents", [{}])[0]
                           .get("gridRenderer", {})
                           .get("items", [])
            )
            for item in items[:max_results]:
                renderer = item.get("richItemRenderer", {}).get("content", {}).get("videoRenderer") \
                        or item.get("gridVideoRenderer")
                if not renderer:
                    continue
                video_id = renderer.get("videoId", "")
                title_runs = renderer.get("title", {}).get("runs", [{}])
                title = title_runs[0].get("text", "") if title_runs else ""
                pub = renderer.get("publishedTimeText", {}).get("simpleText", "")
                if video_id and title:
                    videos.append({"video_id": video_id, "title": title, "published_at": pub})
            if videos:
                break
    except (KeyError, IndexError):
        pass

    return videos


def get_latest_videos(channel_id: str, max_results: int = 5) -> list[dict]:
    """Get latest videos from a YouTube channel (RSS first, page scrape as fallback)."""
    try:
        videos = _videos_from_rss(channel_id, max_results)
        if videos:
            return videos
        print(f"  RSS empty, trying page scrape...")
    except Exception as e:
        print(f"  RSS failed ({e}), trying page scrape...")

    try:
        return _videos_from_page(channel_id, max_results)
    except Exception as e:
        print(f"  Error fetching videos for {channel_id}: {e}")
        return []

# ── Summary (Claude browser) ─────────────────────────────

def generate_summary(transcript: str, title: str) -> str:
    """Generate investment summary via Claude browser automation."""
    from backend.claude_browser import generate_summary as _claude_summary
    return _claude_summary(transcript, title)

# ── Hashtag Generation (Claude browser) ──────────────────

def generate_hashtags(summary_body: str, channel_name: str) -> str:
    """Generate 5 keyword hashtags + 1 channel hashtag via Claude browser."""
    from backend.claude_browser import generate_hashtags as _claude_hashtags
    return _claude_hashtags(summary_body, channel_name)


# ── Email Notification ───────────────────────────────────

GMAIL_USER = "yocoppp@gmail.com"


def _read_env_value(key: str) -> str:
    """Read a single key from .env file directly (bypasses os.environ cache)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return os.environ.get(key, "")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(key, "")


def send_notification_email(subject: str, body: str) -> None:
    """Send notification email via Gmail SMTP App Password."""
    app_password = _read_env_value("GMAIL_APP_PASSWORD")
    if not app_password:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD not set in .env\n"
            "  See: myaccount.google.com/apppasswords"
        )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(GMAIL_USER, app_password)
        smtp.sendmail(GMAIL_USER, [GMAIL_USER], msg.as_string())


# ── Main Commands ────────────────────────────────────────

def fetch_channel(channel_id: str):
    conn = get_db()
    print(f"Fetching channel: {channel_id}")
    
    videos = get_latest_videos(channel_id)
    print(f"  Found {len(videos)} recent videos")
    
    new_count = 0
    for v in videos:
        # Check if already processed
        existing = conn.execute("SELECT id FROM episodes WHERE video_id=?", (v["video_id"],)).fetchone()
        if existing:
            continue
        
        print(f"  New video: {v['title'][:60]}")
        
        # Get transcript
        transcript = get_youtube_transcript(v["video_id"])
        
        if not transcript:
            print(f"  Skipping (no transcript)")
            continue
        
        # Save transcript
        transcript_path = TRANSCRIPTS_DIR / f"{v['video_id']}.txt"
        transcript_path.write_text(transcript, encoding="utf-8")
        
        # Generate summary
        print(f"  Generating summary...")
        summary_md = generate_summary(transcript, v["title"])
        
        # Add metadata header
        now = datetime.now().strftime("%Y-%m-%d")
        header = f"---\ntitle: {v['title']}\nvideo_id: {v['video_id']}\nchannel_id: {channel_id}\npublished: {v.get('published_at', '')}\nprocessed: {now}\n---\n\n# {v['title']}\n\n🔗 [YouTube 觀看原片](https://youtube.com/watch?v={v['video_id']})\n\n"
        full_md = header + summary_md
        
        summary_path = SUMMARIES_DIR / f"{v['video_id']}.md"
        summary_path.write_text(full_md, encoding="utf-8")
        
        # Save to DB
        conn.execute("""
            INSERT OR IGNORE INTO episodes 
            (channel_id, video_id, title, published_at, transcript_path, summary_path, processed)
            VALUES (?,?,?,?,?,?,1)
        """, (channel_id, v["video_id"], v["title"], v.get("published_at"), 
              str(transcript_path), str(summary_path)))
        conn.commit()
        new_count += 1
        print(f"  ✓ Done: {v['title'][:50]}")
    
    # Update last_checked
    conn.execute("UPDATE channels SET last_checked=CURRENT_TIMESTAMP WHERE channel_id=?", (channel_id,))
    conn.commit()
    conn.close()
    print(f"  Processed {new_count} new videos")

def fetch_all():
    conn = get_db()
    channels = conn.execute("SELECT channel_id FROM channels WHERE active=1").fetchall()
    conn.close()
    
    for ch in channels:
        fetch_channel(ch["channel_id"])

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: worker.py [fetch-all | fetch <channel_id> | summarize <video_id>]")
        sys.exit(1)
    
    cmd = args[0]
    if cmd == "fetch-all":
        fetch_all()
    elif cmd == "fetch" and len(args) > 1:
        fetch_channel(args[1])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
