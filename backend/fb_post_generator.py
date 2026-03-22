"""
Generate Facebook-ready post text from investment summary markdown files.

Format: plain-text with emojis and Unicode symbols that render well on
Facebook (no HTML/CSS support in posts). Mimics the website's section
structure and visual style as closely as a plain-text medium allows.
"""
from __future__ import annotations

import re
from pathlib import Path

# ── Section emoji mapping ─────────────────────────────────
_SECTION_EMOJIS: dict[str, str] = {
    "本期主題總覽":        "📋",
    "各主題重點":          "📑",
    "核心觀點":            "💡",
    "提及標的":            "🎯",
    "關鍵數據":            "📊",
    "創作者點出的機會":    "🚀",
    "風險提示":            "⚠️",
    "創作者建議的觀察方向": "🔭",
    # Legacy aliases
    "投資機會":            "🚀",
    "個人行動建議":        "🔭",
}

_DIVIDER = "─" * 30


# ── Markdown parser ───────────────────────────────────────

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Return (meta dict, body text after frontmatter)."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    meta: dict[str, str] = {}
    for line in content[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    body = content[end + 3:].strip()
    return meta, body


def _strip_markdown_bullet(line: str) -> str:
    """
    Convert a markdown bullet line to Facebook-friendly text.

    * `**Bold label:** rest`  →  ▸ Bold label：rest
    * `* plain text`          →  ▸ plain text
    """
    # Strip leading list marker (* or -)
    line = re.sub(r"^\s*[-*]\s+", "", line).strip()
    if not line:
        return ""

    # Skip horizontal rule remnants like "---" or "─────"
    if re.match(r"^[-─]{2,}$", line):
        return ""

    # **Bold text:** rest  →  Bold text：rest
    m = re.match(r"\*\*(.+?)\*\*[:：]?\s*(.*)", line)
    if m:
        label = m.group(1).strip().rstrip("：:")
        rest = m.group(2).strip()
        # Strip leading punctuation from rest (e.g. "，xxx" after bold label)
        rest = re.sub(r"^[，,、]\s*", "", rest)
        text = f"{label}：{rest}" if rest else label
    else:
        # Remove any remaining **bold** markers
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", line).strip()

    # Remove inline markdown emphasis
    text = re.sub(r"[*_`]", "", text).strip()
    return f"▸ {text}" if text else ""


def _parse_sections(body: str) -> list[tuple[str, list[str]]]:
    """
    Parse markdown body into a list of (section_name, [bullet_lines]).
    Skips the leading h1 title and the YouTube link line.
    """
    sections: list[tuple[str, list[str]]] = []
    current_section: str | None = None
    current_lines: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()

        # h2 section header
        if line.startswith("## "):
            if current_section is not None:
                sections.append((current_section, current_lines))
            current_section = line[3:].strip()
            current_lines = []
            continue

        # Skip h1 title and YouTube link
        if line.startswith("# ") or line.startswith("🔗") or line.startswith("[YouTube"):
            continue

        # Only collect bullets inside a section
        if current_section is None:
            continue

        if line.startswith("*") or line.startswith("-"):
            converted = _strip_markdown_bullet(line)
            if converted:
                current_lines.append(converted)

    if current_section is not None and current_lines:
        sections.append((current_section, current_lines))

    return sections


# ── Main generator ────────────────────────────────────────

def generate_facebook_post(md_path: Path) -> str:
    """
    Read a summary markdown file and return a Facebook-ready post string.
    """
    content = md_path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(content)

    title = meta.get("title", md_path.stem)
    channel_name = meta.get("channel_name", "")
    video_id = meta.get("video_id", "")
    source_type = meta.get("source_type", "youtube")
    hashtags = meta.get("hashtags", "")
    source_url = meta.get("source_url", "")

    # Build YouTube / source link
    if source_type == "newsletter":
        link_line = f"🔗 閱讀原文：{source_url}" if source_url else ""
    else:
        link_line = f"🔗 YouTube 觀看原片：https://youtube.com/watch?v={video_id}" if video_id else ""

    # ── Header block ──────────────────────────────────────
    lines: list[str] = []
    lines.append("[投資YT重點摘要]")
    if channel_name:
        lines.append(f"📺 {channel_name}")
    lines.append(f"📈 {title}")
    lines.append("")

    # ── Section blocks ────────────────────────────────────
    sections = _parse_sections(body)

    for section_name, bullets in sections:
        if not bullets:
            continue
        emoji = _SECTION_EMOJIS.get(section_name, "▪️")
        lines.append(_DIVIDER)
        lines.append("")
        lines.append(f"{emoji} {section_name}")
        lines.append("")
        lines.extend(bullets)
        lines.append("")

    # ── Footer ────────────────────────────────────────────
    lines.append(_DIVIDER)
    lines.append("")
    if link_line:
        lines.append(link_line)
        lines.append("")
    if hashtags:
        lines.append(hashtags)

    return "\n".join(lines).strip()
