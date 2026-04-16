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
CARDS_SHORTS_DIR = BASE_DIR / "data" / "cards_shorts"
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
        # Return raw only if it already looks like YYYY-MM-DD; otherwise discard
        if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
            return raw
        return ""


def _episode_sort_key(episode: dict) -> tuple:
    """Sort by published_at desc first, then EP number desc as tiebreaker."""
    m = re.search(r'EP(\d+)', episode.get("title", ""), re.IGNORECASE)
    ep_num = int(m.group(1)) if m else 0
    date = episode.get("published_at") or episode.get("processed_at") or ""
    return (date, ep_num)


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
            source_type = meta.get("source_type", "youtube")
            source_url = meta.get("source_url", "")

            # Collect card URLs — prefer Shorts cards, fall back to landscape cards
            _shorts_src = CARDS_SHORTS_DIR / channel_name / video_id if channel_name else CARDS_SHORTS_DIR / video_id
            _landscape_src = CARDS_DIR / channel_name / video_id if channel_name else CARDS_DIR / video_id
            card_src_dir = _shorts_src if _shorts_src.exists() else _landscape_src
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
                "source_type": source_type,
                "source_url": source_url,
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
    _build_cooccurrence_json(SITE_DATA_DIR, generated_at)
    _build_weekly_json(SITE_DATA_DIR, generated_at)
    _build_rss_feed(SITE_DIR, episodes, generated_at)

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

        # All entities sorted by mention count (no limit — entity search needs full set)
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


def _enrich_us_fundamentals(entities: list[dict]) -> None:
    """Fetch Yahoo Finance fundamentals for US and Taiwan stock tickers (in-place)."""
    import time

    try:
        import yfinance as yf
    except ImportError:
        print("  (skipping fundamentals — yfinance not installed)")
        return

    eligible = [e for e in entities if e.get("ticker")]
    if not eligible:
        return

    def _is_tw(ticker: str) -> bool:
        return bool(re.fullmatch(r"\d{4,5}", ticker))

    # Deduplicate by ticker
    seen: dict[str, dict] = {}
    for e in eligible:
        seen.setdefault(e["ticker"].upper(), e)

    print(f"  Fetching fundamentals for {len(seen)} tickers…")

    info_map: dict[str, dict] = {}
    for ticker, _e in seen.items():
        # For Taiwan tickers, try .TW then .TWO
        yf_symbols = ([f"{ticker}.TW", f"{ticker}.TWO"] if _is_tw(ticker) else [ticker])
        info = {}
        for sym in yf_symbols:
            try:
                raw = yf.Ticker(sym).info or {}
                if raw.get("trailingPE") or raw.get("marketCap"):
                    info = raw
                    break
            except Exception:
                pass
            time.sleep(0.2)

        pe         = info.get("trailingPE")
        fwd_pe     = info.get("forwardPE")
        mkt_cap    = info.get("marketCap")
        w52_low    = info.get("fiftyTwoWeekLow")
        w52_high   = info.get("fiftyTwoWeekHigh")
        price      = info.get("currentPrice") or info.get("regularMarketPrice")
        eps_growth = info.get("earningsGrowth")
        rev_growth = info.get("revenueGrowth")
        currency   = info.get("currency", "USD")

        if any(v is not None for v in [pe, fwd_pe, mkt_cap]):
            info_map[ticker] = {
                "pe":         round(pe, 1)         if pe         is not None else None,
                "fwd_pe":     round(fwd_pe, 1)     if fwd_pe     is not None else None,
                "mkt_cap":    mkt_cap,
                "currency":   currency,
                "w52_low":    round(w52_low, 2)    if w52_low    is not None else None,
                "w52_high":   round(w52_high, 2)   if w52_high   is not None else None,
                "price":      round(price, 2)      if price      is not None else None,
                "eps_growth": round(eps_growth, 4) if eps_growth is not None else None,
                "rev_growth": round(rev_growth, 4) if rev_growth is not None else None,
            }

    enriched = 0
    for e in eligible:
        sym = e["ticker"].upper()
        if sym in info_map:
            e["fundamentals"] = info_map[sym]
            enriched += 1

    print(f"  ✓ enriched {enriched}/{len(eligible)} entities with fundamentals")


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

        _enrich_us_fundamentals(entities)

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


def _build_cooccurrence_json(site_data_dir: Path, generated_at: str) -> None:
    """Generate docs/data/cooccurrence.json: entity co-occurrence pairs from mentions table."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "mentions" not in tables:
            conn.close()
            return

        # Fetch entity names grouped by video_id
        rows = conn.execute(
            "SELECT video_id, entity_name FROM mentions ORDER BY video_id"
        ).fetchall()
        conn.close()

        # Build map: video_id → set of entity names
        by_video: dict[str, set] = {}
        for row in rows:
            vid = row["video_id"]
            if vid not in by_video:
                by_video[vid] = set()
            by_video[vid].add(row["entity_name"])

        # Count co-occurrences
        from collections import defaultdict
        pair_counts: dict[tuple, int] = defaultdict(int)
        for entities in by_video.values():
            entity_list = sorted(entities)
            for i, a in enumerate(entity_list):
                for b in entity_list[i + 1:]:
                    pair_counts[(a, b)] += 1

        # Build per-entity top-10 related entities (count >= 2)
        # Fetch ticker for each entity (max ticker seen)
        ticker_rows = conn.execute if False else None  # ticker lookup below
        conn2 = sqlite3.connect(DB_PATH)
        conn2.row_factory = sqlite3.Row
        ticker_map: dict[str, str] = {}
        for row in conn2.execute("SELECT entity_name, MAX(ticker) AS ticker FROM mentions GROUP BY entity_name").fetchall():
            ticker_map[row["entity_name"]] = row["ticker"] or ""
        conn2.close()

        related: dict[str, list] = defaultdict(list)
        for (a, b), count in pair_counts.items():
            if count < 2:
                continue
            related[a].append({"name": b, "ticker": ticker_map.get(b, ""), "count": count})
            related[b].append({"name": a, "ticker": ticker_map.get(a, ""), "count": count})

        # Sort each entity's list by count desc, keep top 10
        entities_out = {}
        for entity, peers in related.items():
            peers_sorted = sorted(peers, key=lambda x: x["count"], reverse=True)[:10]
            entities_out[entity] = peers_sorted

        out = {
            "entities": entities_out,
            "generated_at": generated_at,
        }
        out_path = site_data_dir / "cooccurrence.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ docs/data/cooccurrence.json — {len(entities_out)} entities with co-occurrence data")
    except Exception as e:
        print(f"  ⚠️ cooccurrence.json 產生失敗：{e}")


def _parse_weekly_frontmatter(content: str, stem: str) -> dict:
    """Extract YAML frontmatter fields from a weekly MD file."""
    meta: dict = {}
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            for line in content[3:end].splitlines():
                m = re.match(r'^(\w+):\s*(.*)', line)
                if m:
                    meta[m.group(1)] = m.group(2).strip()
    meta.setdefault("week", stem)
    return meta


def _build_weekly_json(site_data_dir: Path, generated_at: str) -> None:
    """Copy all weekly digests to docs/data/weekly/ and write weekly_meta.json."""
    weekly_dir = BASE_DIR / "data" / "weekly"
    no_meta = {"available": False, "generated_at": generated_at}

    if not weekly_dir.exists():
        (site_data_dir / "weekly_meta.json").write_text(
            json.dumps(no_meta, ensure_ascii=False), encoding="utf-8"
        )
        print("  (skipping weekly — data/weekly/ not found)")
        return

    md_files = sorted(weekly_dir.glob("*.md"), reverse=True)
    if not md_files:
        (site_data_dir / "weekly_meta.json").write_text(
            json.dumps(no_meta, ensure_ascii=False), encoding="utf-8"
        )
        print("  (skipping weekly — no .md files in data/weekly/)")
        return

    # Copy all weekly MDs to docs/data/weekly/
    out_weekly_dir = site_data_dir / "weekly"
    out_weekly_dir.mkdir(exist_ok=True)
    index = []
    for f in md_files:
        content = f.read_text(encoding="utf-8")
        meta = _parse_weekly_frontmatter(content, f.stem)
        shutil.copy2(f, out_weekly_dir / f.name)
        index.append({
            "week":      meta.get("week", f.stem),
            "generated": meta.get("generated", ""),
            "episodes":  int(meta.get("episodes", 0) or 0),
            "filename":  f.name,
        })

    latest_meta = index[0]

    # Keep weekly_latest.md for backward compatibility
    shutil.copy2(md_files[0], site_data_dir / "weekly_latest.md")

    # Write weekly_meta.json with full index
    (site_data_dir / "weekly_meta.json").write_text(json.dumps({
        "available":    True,
        "week":         latest_meta["week"],
        "generated":    latest_meta["generated"],
        "episodes":     latest_meta["episodes"],
        "generated_at": generated_at,
        "index":        index,          # all weeks, newest first
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ docs/data/weekly_latest.md — week {latest_meta['week']}")
    print(f"✓ docs/data/weekly_meta.json")


def _build_rss_feed(site_dir: Path, episodes: list, generated_at: str) -> None:
    """Generate docs/feed.xml — standard RSS 2.0 with the 30 most recent episodes."""
    from email.utils import formatdate
    import time

    SITE_URL = "https://ultrahikerpp.github.io/invest-digest/"

    def _pub_date(date_str: str) -> str:
        """Convert YYYY-MM-DD to RFC 822 format for RSS pubDate."""
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            # formatdate expects a Unix timestamp
            ts = dt.replace(tzinfo=timezone.utc).timestamp()
            return formatdate(ts, usegmt=True)
        except ValueError:
            return ""

    def _xml_escape(text: str) -> str:
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    recent = episodes[:30]

    items_xml = []
    for ep in recent:
        title = _xml_escape(ep.get("title", ""))
        channel_id = ep.get("channel_id", "")
        video_id = ep.get("video_id", "")
        channel_name = _xml_escape(ep.get("channel_name", ""))
        link = f"{SITE_URL}#/channel/{channel_id}"
        guid = f"{SITE_URL}#/episode/{video_id}"
        description = _xml_escape(f"{ep.get('channel_name', '')} — {ep.get('title', '')}")
        pub_date = _pub_date(ep.get("published_at", ""))

        pub_date_tag = f"    <pubDate>{pub_date}</pubDate>\n" if pub_date else ""
        items_xml.append(
            f"  <item>\n"
            f"    <title>{title}</title>\n"
            f"    <link>{link}</link>\n"
            f"    <guid isPermaLink=\"false\">{guid}</guid>\n"
            f"{pub_date_tag}"
            f"    <description>{description}</description>\n"
            f"    <category>{channel_name}</category>\n"
            f"  </item>"
        )

    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        '<channel>\n'
        '  <title>Ultra Investment Digest｜財經投資頻道重點摘要</title>\n'
        f'  <link>{SITE_URL}</link>\n'
        '  <description>AI 生成的台灣投資 Podcast 摘要</description>\n'
        f"  <lastBuildDate>{formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)}</lastBuildDate>\n"
        + "\n".join(items_xml) + "\n"
        '</channel>\n'
        '</rss>\n'
    )

    out_path = site_dir / "feed.xml"
    out_path.write_text(rss, encoding="utf-8")
    print(f"✓ docs/feed.xml — {len(recent)} episodes")


if __name__ == "__main__":
    build()
