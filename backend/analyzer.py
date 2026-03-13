#!/usr/bin/env python3
"""
Analyzer: DB operations for mentions and episode_industries tables.

Tables managed here:
  mentions          — per-episode entity mentions with sentiment
  episode_industries — per-episode industry tags
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "subscriptions.db"


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
        conn.execute(
            """
            INSERT INTO mentions
                (video_id, channel_id, entity_name, entity_type, ticker, sentiment, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                channel_id,
                m.get("name", ""),
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
