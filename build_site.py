#!/usr/bin/env python3
"""
Static site builder for GitHub Pages.

Reads data/summaries/*.md → writes site/data/episodes.json + copies site/summaries/*.md
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
SUMMARIES_DIR = BASE_DIR / "data" / "summaries"
CARDS_DIR = BASE_DIR / "data" / "cards"
CHANNELS_FILE = BASE_DIR / "channels.json"
SITE_DIR = BASE_DIR / "docs"
SITE_SUMMARIES_DIR = SITE_DIR / "summaries"
SITE_CARDS_DIR = SITE_DIR / "cards"
SITE_DATA_DIR = SITE_DIR / "data"


def _load_channels() -> dict[str, dict]:
    """Return mapping of channel_id → channel info."""
    if not CHANNELS_FILE.exists():
        return {}
    with open(CHANNELS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {ch["channel_id"]: ch for ch in data.get("channels", [])}


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-style frontmatter (key: value) from markdown. Returns (meta, body)."""
    meta: dict[str, str] = {}
    body = content

    if not content.startswith("---"):
        return meta, body

    end = content.find("---", 3)
    if end == -1:
        return meta, body

    fm_block = content[3:end]
    body = content[end + 3:].lstrip("\n")

    for line in fm_block.splitlines():
        m = re.match(r'^(\w+):\s*(.*)', line)
        if m:
            meta[m.group(1)] = m.group(2).strip()

    return meta, body


def _normalize_date(raw: str) -> str:
    """Try to parse ISO datetime to YYYY-MM-DD; return raw if not parseable."""
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        # Could be relative (e.g. "1 天前") or already YYYY-MM-DD
        return raw


def _episode_sort_key(episode: dict) -> tuple:
    """Sort by EP number desc (EP639 > EP638...), fallback to processed_at desc."""
    m = re.search(r'EP(\d+)', episode.get("title", ""), re.IGNORECASE)
    ep_num = int(m.group(1)) if m else 0
    return (ep_num, episode.get("processed_at") or "")


def build():
    channels = _load_channels()

    SITE_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    SITE_CARDS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    md_files = sorted(SUMMARIES_DIR.glob("*.md"))
    if not md_files:
        print("No summaries found in data/summaries/")
        episodes = []
    else:
        episodes = []
        for md_path in md_files:
            content = md_path.read_text(encoding="utf-8")
            meta, _ = _parse_frontmatter(content)

            video_id = meta.get("video_id") or md_path.stem
            channel_id = meta.get("channel_id", "")
            title = meta.get("title", md_path.stem)

            # Resolve channel_name: frontmatter first, then channels.json fallback
            channel_name = meta.get("channel_name", "")
            channel_thumbnail = ""
            if not channel_name and channel_id in channels:
                channel_name = channels[channel_id]["name"]
                channel_thumbnail = channels[channel_id].get("thumbnail_url", "")
            elif channel_id in channels:
                channel_thumbnail = channels[channel_id].get("thumbnail_url", "")

            published_at = _normalize_date(meta.get("published", ""))
            processed_at = _normalize_date(meta.get("processed", ""))

            # Collect card URLs if cards exist for this video
            card_src_dir = CARDS_DIR / video_id
            card_urls: list[str] = []
            if card_src_dir.exists():
                card_files = sorted(card_src_dir.glob("card_*.png"))
                card_urls = [f"cards/{video_id}/{p.name}" for p in card_files]
                dest_card_dir = SITE_CARDS_DIR / video_id
                shutil.copytree(card_src_dir, dest_card_dir, dirs_exist_ok=True)

            episodes.append({
                "video_id": video_id,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "channel_thumbnail": channel_thumbnail,
                "title": title,
                "published_at": published_at,
                "processed_at": processed_at,
                "summary_url": f"summaries/{video_id}.md",
                "cards": card_urls,
            })

            # Copy summary file to site/
            dest = SITE_SUMMARIES_DIR / md_path.name
            shutil.copy2(md_path, dest)
            print(f"  Copied {md_path.name}")

        # Sort by EP number desc, fallback to processed_at desc
        episodes.sort(key=_episode_sort_key, reverse=True)

    index = {
        "episodes": episodes,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out_path = SITE_DATA_DIR / "episodes.json"
    out_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ docs/data/episodes.json — {len(episodes)} episodes")
    print(f"✓ docs/summaries/ — {len(episodes)} files")
    print(f"✓ Build complete → {SITE_DIR}")


if __name__ == "__main__":
    build()
