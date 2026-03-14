#!/usr/bin/env python3
"""
Static site builder for GitHub Pages.

Reads data/summaries/*.md → writes site/data/episodes.json + copies site/summaries/*.md
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
SUMMARIES_DIR = BASE_DIR / "data" / "summaries"
CARDS_DIR = BASE_DIR / "data" / "cards"
CHANNELS_FILE = BASE_DIR / "channels.json"
DB_PATH = BASE_DIR / "data" / "subscriptions.db"
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
    """Sort by EP number desc (EP639 > EP638...), fallback to published_at desc."""
    m = re.search(r'EP(\d+)', episode.get("title", ""), re.IGNORECASE)
    ep_num = int(m.group(1)) if m else 0
    return (ep_num, episode.get("published_at") or episode.get("processed_at") or "")


def build():
    channels = _load_channels()

    SITE_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    SITE_CARDS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    md_files = sorted(SUMMARIES_DIR.glob("*/*.md"))
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
            hashtags = meta.get("hashtags", "")

            # Collect card URLs if cards exist for this video
            card_src_dir = CARDS_DIR / channel_name / video_id if channel_name else CARDS_DIR / video_id
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
                "hashtags": hashtags,
            })

            # Copy summary file to site/
            dest = SITE_SUMMARIES_DIR / md_path.name
            shutil.copy2(md_path, dest)
            print(f"  Copied {md_path.name}")

        # Sort by EP number desc, fallback to processed_at desc
        episodes.sort(key=_episode_sort_key, reverse=True)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    index = {
        "episodes": episodes,
        "generated_at": generated_at,
    }
    out_path = SITE_DATA_DIR / "episodes.json"
    out_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate mentions.json, divergence.json, entity_history.json, and flips.json from analysis DB
    _build_mentions_json(SITE_DATA_DIR, generated_at)
    _build_divergence_json(SITE_DATA_DIR, channels, generated_at)
    _build_entity_history_json(SITE_DATA_DIR, channels, generated_at)
    _build_flips_json(SITE_DATA_DIR, generated_at)

    print(f"\n✓ docs/data/episodes.json — {len(episodes)} episodes")
    print(f"✓ docs/summaries/ — {len(episodes)} files")
    print(f"✓ Build complete → {SITE_DIR}")


def _build_mentions_json(site_data_dir: Path, generated_at: str) -> None:
    """Generate docs/data/mentions.json from the analysis DB tables."""
    if not DB_PATH.exists():
        print("  (skipping mentions.json — DB not found)")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # Check that analysis tables exist
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "mentions" not in tables or "episode_industries" not in tables:
            print("  (skipping mentions.json — analysis tables not yet created)")
            conn.close()
            return

        # Trending: top entities across all time for static export
        trending_rows = conn.execute("""
            SELECT
                entity_name  AS name,
                MAX(ticker)  AS ticker,
                COUNT(*)                                            AS count,
                SUM(CASE WHEN sentiment='看多' THEN 1 ELSE 0 END) AS bullish,
                SUM(CASE WHEN sentiment='看空' THEN 1 ELSE 0 END) AS bearish,
                SUM(CASE WHEN sentiment='中立' THEN 1 ELSE 0 END) AS neutral
            FROM mentions
            GROUP BY entity_name
            ORDER BY count DESC
            LIMIT 20
        """).fetchall()

        industry_rows = conn.execute("""
            SELECT industry AS name, COUNT(*) AS count
            FROM episode_industries
            GROUP BY industry
            ORDER BY count DESC
        """).fetchall()

        # By-episode index
        mentions_rows = conn.execute(
            "SELECT video_id, entity_name FROM mentions ORDER BY video_id"
        ).fetchall()
        industries_rows = conn.execute(
            "SELECT video_id, industry FROM episode_industries ORDER BY video_id"
        ).fetchall()

        conn.close()

        by_episode: dict = {}
        for row in mentions_rows:
            vid = row["video_id"]
            if vid not in by_episode:
                by_episode[vid] = {"industries": [], "mentions": []}
            by_episode[vid]["mentions"].append(row["entity_name"])
        for row in industries_rows:
            vid = row["video_id"]
            if vid not in by_episode:
                by_episode[vid] = {"industries": [], "mentions": []}
            if row["industry"] not in by_episode[vid]["industries"]:
                by_episode[vid]["industries"].append(row["industry"])

        mentions_index = {
            "trending": [
                {
                    "name": r["name"],
                    "ticker": r["ticker"],
                    "count": r["count"],
                    "bullish": r["bullish"],
                    "bearish": r["bearish"],
                    "neutral": r["neutral"],
                }
                for r in trending_rows
            ],
            "industries": [{"name": r["name"], "count": r["count"]} for r in industry_rows],
            "by_episode": by_episode,
            "generated_at": generated_at,
        }

        out_path = site_data_dir / "mentions.json"
        out_path.write_text(json.dumps(mentions_index, ensure_ascii=False, indent=2), encoding="utf-8")
        trending_count = len(mentions_index["trending"])
        print(f"✓ docs/data/mentions.json — {trending_count} trending entities")

    except Exception as e:
        print(f"  ⚠️ mentions.json 產生失敗：{e}")


def _build_divergence_json(
    site_data_dir: Path,
    channels: dict[str, dict],
    generated_at: str,
) -> None:
    """Generate docs/data/divergence.json with cross-channel sentiment comparison."""
    if not DB_PATH.exists():
        print("  (skipping divergence.json — DB not found)")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "mentions" not in tables:
            print("  (skipping divergence.json — mentions table not yet created)")
            conn.close()
            return

        from backend.analyzer import get_cross_channel_divergence

        channel_names = {cid: info["name"] for cid, info in channels.items()}
        entities = get_cross_channel_divergence(
            conn, days=90, min_channels=2, channel_names=channel_names
        )
        conn.close()

        out = {
            "entities": entities,
            "generated_at": generated_at,
        }
        out_path = site_data_dir / "divergence.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ docs/data/divergence.json — {len(entities)} cross-channel entities")

    except Exception as e:
        print(f"  ⚠️ divergence.json 產生失敗：{e}")


def _build_entity_history_json(site_data_dir: Path, channels: dict, generated_at: str) -> None:
    """Generate docs/data/entity_history.json: per-entity episode history with sentiment."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "mentions" not in tables:
            conn.close()
            return

        rows = conn.execute("""
            SELECT
                m.entity_name,
                m.ticker,
                m.sentiment,
                m.video_id,
                m.channel_id,
                m.processed_at,
                e.title,
                e.published_at
            FROM mentions m
            LEFT JOIN episodes e ON m.video_id = e.video_id
            ORDER BY m.entity_name, COALESCE(e.published_at, m.processed_at) DESC
        """).fetchall()
        conn.close()

        channel_names = {cid: info["name"] for cid, info in channels.items()}

        entities: dict[str, list] = {}
        for row in rows:
            name = row["entity_name"]
            if name not in entities:
                entities[name] = []
            entities[name].append({
                "video_id": row["video_id"],
                "channel_id": row["channel_id"],
                "channel_name": channel_names.get(row["channel_id"], row["channel_id"]),
                "title": row["title"] or row["video_id"],
                "published_at": row["published_at"] or row["processed_at"] or "",
                "sentiment": row["sentiment"] or "中立",
                "ticker": row["ticker"] or "",
            })

        out = {
            "entities": entities,
            "generated_at": generated_at,
        }
        out_path = site_data_dir / "entity_history.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ docs/data/entity_history.json — {len(entities)} entities")
    except Exception as e:
        print(f"  ⚠️ entity_history.json 產生失敗：{e}")


def _build_flips_json(site_data_dir: Path, generated_at: str) -> None:
    """Generate docs/data/flips.json: entities with sentiment reversal in last 60 days."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "mentions" not in tables:
            conn.close()
            return

        # Period 1: 30-60 days ago; Period 2: last 30 days
        p1_rows = conn.execute("""
            SELECT entity_name, MAX(ticker) AS ticker,
                   SUM(CASE WHEN sentiment='看多' THEN 1 ELSE 0 END) AS bullish,
                   SUM(CASE WHEN sentiment='看空' THEN 1 ELSE 0 END) AS bearish,
                   SUM(CASE WHEN sentiment='中立' THEN 1 ELSE 0 END) AS neutral,
                   COUNT(*) AS total
            FROM mentions
            WHERE processed_at >= DATE('now', '-60 days')
              AND processed_at < DATE('now', '-30 days')
            GROUP BY entity_name
            HAVING total >= 2
        """).fetchall()

        p2_rows = conn.execute("""
            SELECT entity_name, MAX(ticker) AS ticker,
                   SUM(CASE WHEN sentiment='看多' THEN 1 ELSE 0 END) AS bullish,
                   SUM(CASE WHEN sentiment='看空' THEN 1 ELSE 0 END) AS bearish,
                   SUM(CASE WHEN sentiment='中立' THEN 1 ELSE 0 END) AS neutral,
                   COUNT(*) AS total
            FROM mentions
            WHERE processed_at >= DATE('now', '-30 days')
            GROUP BY entity_name
            HAVING total >= 2
        """).fetchall()
        conn.close()

        def _dominant(bull, bear, neutral):
            if bull > bear and bull > neutral:
                return "看多"
            if bear > bull and bear > neutral:
                return "看空"
            return "中立"

        p1_map = {r["entity_name"]: dict(r) for r in p1_rows}
        p2_map = {r["entity_name"]: dict(r) for r in p2_rows}

        flips = []
        for name, p2 in p2_map.items():
            if name not in p1_map:
                continue
            p1 = p1_map[name]
            s1 = _dominant(p1["bullish"], p1["bearish"], p1["neutral"])
            s2 = _dominant(p2["bullish"], p2["bearish"], p2["neutral"])
            if s1 != s2 and s1 != "中立" and s2 != "中立":
                flips.append({
                    "name": name,
                    "ticker": p2["ticker"] or "",
                    "before": s1,
                    "after": s2,
                    "before_count": p1["total"],
                    "after_count": p2["total"],
                })

        out = {"flips": flips, "generated_at": generated_at}
        out_path = site_data_dir / "flips.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ docs/data/flips.json — {len(flips)} sentiment flips")
    except Exception as e:
        print(f"  ⚠️ flips.json 產生失敗：{e}")


if __name__ == "__main__":
    build()
