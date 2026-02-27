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
import urllib.request
import urllib.parse
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

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
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
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

# ── Claude API Summary ───────────────────────────────────

def generate_summary(transcript: str, title: str) -> str:
    """Call Gemini API to generate investment summary"""
    if not GEMINI_API_KEY:
        return f"# {title}\n\n⚠️ 請設定 GEMINI_API_KEY 環境變數以啟用 AI 摘要功能。\n\n## 逐字稿原文\n\n{transcript[:2000]}..."

    prompt = f"""你是一位專業的投資分析師助理。請分析以下投資 Podcast / YouTube 影片的逐字稿，產出結構化的投資重點摘要。

影片標題：{title}

逐字稿：
{transcript[:8000]}

請用繁體中文產出以下格式的 Markdown 摘要：

## 核心觀點
（3-5個主要投資觀點）

## 提及標的
（股票、ETF、產業、市場等，若無則標注「本集未提及具體標的」）

## 關鍵數據
（重要數字、指標、時間點）

## 投資機會
（值得關注的機會）

## 風險提示
（提到的風險或注意事項）

## 個人行動建議
（根據內容，投資人可以採取的具體行動）
"""

    try:
        payload = json.dumps({
            "contents": [
                {"parts": [{"text": prompt}]}
            ],
            "generationConfig": {"maxOutputTokens": 8192}
        }).encode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}")

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        return f"# {title}\n\n⚠️ AI 摘要生成失敗：{e}\n\n## 逐字稿前段\n\n{transcript[:1000]}"

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
