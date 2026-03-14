#!/usr/bin/env python3
"""
Analyzer: DB operations for mentions and episode_industries tables.

Tables managed here:
  mentions          — per-episode entity mentions with sentiment
  episode_industries — per-episode industry tags
"""
from __future__ import annotations

import json as _json
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "subscriptions.db"

_ALIASES_PATH = Path(__file__).parent.parent / "entity_aliases.json"
_ALIASES: dict[str, str] | None = None


def _load_aliases() -> dict[str, str]:
    global _ALIASES
    if _ALIASES is None:
        if _ALIASES_PATH.exists():
            with open(_ALIASES_PATH, encoding="utf-8") as f:
                _ALIASES = _json.load(f).get("aliases", {})
        else:
            _ALIASES = {}
    return _ALIASES


def normalize_entity_name(name: str) -> str:
    """Return the canonical name if an alias mapping exists, else return name as-is."""
    return _load_aliases().get(name, name)


def init_tables(conn: sqlite3.Connection) -> None:
    """Create mentions and episode_industries tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id     TEXT NOT NULL,
            channel_id   TEXT NOT NULL,
            entity_name  TEXT NOT NULL,
            entity_type  TEXT,
            ticker       TEXT,
            sentiment    TEXT,
            processed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episode_industries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id     TEXT NOT NULL,
            channel_id   TEXT NOT NULL,
            industry     TEXT NOT NULL,
            processed_at TEXT
        )
    """)
    conn.commit()


def has_analysis(conn: sqlite3.Connection, video_id: str) -> bool:
    """Return True if any mentions or industries already exist for this video."""
    row = conn.execute(
        "SELECT id FROM mentions WHERE video_id=? LIMIT 1", (video_id,)
    ).fetchone()
    if row:
        return True
    row = conn.execute(
        "SELECT id FROM episode_industries WHERE video_id=? LIMIT 1", (video_id,)
    ).fetchone()
    return row is not None


def save_mentions(
    conn: sqlite3.Connection,
    video_id: str,
    channel_id: str,
    mentions: list[dict],
) -> None:
    """Replace all mention records for this video (idempotent)."""
    now = datetime.now().strftime("%Y-%m-%d")
    conn.execute("DELETE FROM mentions WHERE video_id=?", (video_id,))
    for m in mentions:
        normalized_name = normalize_entity_name(m.get("name", ""))
        conn.execute(
            """
            INSERT INTO mentions
                (video_id, channel_id, entity_name, entity_type, ticker, sentiment, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                channel_id,
                normalized_name,
                m.get("type"),
                m.get("ticker") or None,
                m.get("sentiment"),
                now,
            ),
        )
    conn.commit()


def save_industries(
    conn: sqlite3.Connection,
    video_id: str,
    channel_id: str,
    industries: list[str],
) -> None:
    """Replace all industry records for this video (idempotent)."""
    now = datetime.now().strftime("%Y-%m-%d")
    conn.execute("DELETE FROM episode_industries WHERE video_id=?", (video_id,))
    for ind in industries:
        conn.execute(
            """
            INSERT INTO episode_industries (video_id, channel_id, industry, processed_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, channel_id, ind, now),
        )
    conn.commit()


def get_trending_mentions(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Return top 10 most-mentioned entities in the last N days."""
    rows = conn.execute(
        """
        SELECT
            entity_name  AS name,
            MAX(ticker)  AS ticker,
            COUNT(*)                                              AS count,
            SUM(CASE WHEN sentiment='看多' THEN 1 ELSE 0 END)   AS bullish,
            SUM(CASE WHEN sentiment='看空' THEN 1 ELSE 0 END)   AS bearish,
            SUM(CASE WHEN sentiment='中立' THEN 1 ELSE 0 END)   AS neutral
        FROM mentions
        WHERE processed_at >= DATE('now', :offset)
        GROUP BY entity_name
        ORDER BY count DESC
        LIMIT 10
        """,
        {"offset": f"-{days} days"},
    ).fetchall()
    return [dict(r) for r in rows]


def get_industry_stats(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Return industry mention counts for the last N days."""
    rows = conn.execute(
        """
        SELECT industry AS name, COUNT(*) AS count
        FROM episode_industries
        WHERE processed_at >= DATE('now', :offset)
        GROUP BY industry
        ORDER BY count DESC
        """,
        {"offset": f"-{days} days"},
    ).fetchall()
    return [dict(r) for r in rows]


def get_entity_track(conn: sqlite3.Connection, name: str) -> list[dict]:
    """Return all episodes mentioning a specific entity (partial name match)."""
    rows = conn.execute(
        """
        SELECT
            m.video_id,
            m.channel_id,
            m.entity_name,
            m.entity_type,
            m.ticker,
            m.sentiment,
            m.processed_at,
            e.title,
            e.published_at
        FROM mentions m
        LEFT JOIN episodes e ON m.video_id = e.video_id
        WHERE LOWER(m.entity_name) LIKE LOWER(:pattern)
        ORDER BY m.processed_at DESC
        """,
        {"pattern": f"%{name}%"},
    ).fetchall()
    return [dict(r) for r in rows]


def _channel_stance(bullish: int, bearish: int, neutral: int) -> str:
    """Determine a channel's dominant stance from raw mention counts."""
    if bullish > bearish and bullish > neutral:
        return "看多"
    if bearish > bullish and bearish > neutral:
        return "看空"
    return "中立"


def _consensus_label(bull_ch: int, bear_ch: int, neutral_ch: int) -> str:
    """Classify overall consensus/divergence across channels."""
    total = bull_ch + bear_ch + neutral_ch
    if bull_ch > 0 and bear_ch > 0:
        return "多空分歧"
    if bull_ch == total:
        return "看多共識"
    if bear_ch == total:
        return "看空共識"
    if neutral_ch == total:
        return "中立共識"
    # Mixed with neutral: lean toward whichever side dominates
    return "偏多" if bull_ch > bear_ch else "偏空"


def get_cross_channel_divergence(
    conn: sqlite3.Connection,
    days: int = 90,
    min_channels: int = 2,
    channel_names: dict[str, str] | None = None,
) -> list[dict]:
    """
    Find entities mentioned by ≥ min_channels channels within the last N days.
    Returns entities sorted by divergence first (多空分歧 at top), then by total mentions.

    channel_names: optional {channel_id: channel_name} mapping for display.
    """
    rows = conn.execute(
        """
        SELECT
            m.entity_name,
            MAX(m.ticker)                                               AS ticker,
            m.channel_id,
            COUNT(*)                                                    AS mentions,
            SUM(CASE WHEN m.sentiment='看多' THEN 1 ELSE 0 END)        AS bullish,
            SUM(CASE WHEN m.sentiment='看空' THEN 1 ELSE 0 END)        AS bearish,
            SUM(CASE WHEN m.sentiment='中立' THEN 1 ELSE 0 END)        AS neutral
        FROM mentions m
        WHERE m.processed_at >= DATE('now', :offset)
        GROUP BY m.entity_name, m.channel_id
        ORDER BY m.entity_name, mentions DESC
        """,
        {"offset": f"-{days} days"},
    ).fetchall()

    # Aggregate by entity
    entity_map: dict[str, dict] = {}
    for row in rows:
        name = row["entity_name"]
        if name not in entity_map:
            entity_map[name] = {
                "ticker": None,
                "channels": [],
                "total_bullish": 0,
                "total_bearish": 0,
                "total_neutral": 0,
            }
        e = entity_map[name]
        if not e["ticker"]:
            e["ticker"] = row["ticker"]

        b, r, n = row["bullish"], row["bearish"], row["neutral"]
        cnames = channel_names or {}
        e["channels"].append({
            "channel_id": row["channel_id"],
            "channel_name": cnames.get(row["channel_id"], row["channel_id"]),
            "mentions": row["mentions"],
            "bullish": b,
            "bearish": r,
            "neutral": n,
            "stance": _channel_stance(b, r, n),
        })
        e["total_bullish"] += b
        e["total_bearish"] += r
        e["total_neutral"] += n

    result = []
    for name, e in entity_map.items():
        channel_count = len(e["channels"])
        if channel_count < min_channels:
            continue

        total_mentions = e["total_bullish"] + e["total_bearish"] + e["total_neutral"]
        bull_ch = sum(1 for c in e["channels"] if c["stance"] == "看多")
        bear_ch = sum(1 for c in e["channels"] if c["stance"] == "看空")
        neutral_ch = channel_count - bull_ch - bear_ch

        consensus = _consensus_label(bull_ch, bear_ch, neutral_ch)
        # Divergence score: 0 = full consensus, 1 = maximum opposition
        divergence_score = round(2 * min(bull_ch, bear_ch) / channel_count, 3)

        result.append({
            "name": name,
            "ticker": e["ticker"],
            "total_mentions": total_mentions,
            "channel_count": channel_count,
            "total_bullish": e["total_bullish"],
            "total_bearish": e["total_bearish"],
            "total_neutral": e["total_neutral"],
            "bull_channels": bull_ch,
            "bear_channels": bear_ch,
            "neutral_channels": neutral_ch,
            "consensus": consensus,
            "divergence_score": divergence_score,
            "channels": e["channels"],
        })

    # Sort: 多空分歧 first (highest divergence_score), then by total_mentions desc
    result.sort(key=lambda x: (-x["divergence_score"], -x["total_mentions"]))
    return result


def get_by_episode(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return mentions and industries grouped by video_id for static site export."""
    mentions_rows = conn.execute(
        "SELECT video_id, entity_name FROM mentions ORDER BY video_id"
    ).fetchall()
    industries_rows = conn.execute(
        "SELECT video_id, industry FROM episode_industries ORDER BY video_id"
    ).fetchall()

    result: dict[str, dict] = {}

    for row in mentions_rows:
        vid = row["video_id"]
        if vid not in result:
            result[vid] = {"industries": [], "mentions": []}
        result[vid]["mentions"].append(row["entity_name"])

    for row in industries_rows:
        vid = row["video_id"]
        if vid not in result:
            result[vid] = {"industries": [], "mentions": []}
        if row["industry"] not in result[vid]["industries"]:
            result[vid]["industries"].append(row["industry"])

    return result
