"""
Generate 1080x1080 image cards from investment summary markdown files.
Each section becomes one card (1:1 square for Instagram / TikTok).
"""
from PIL import Image, ImageDraw, ImageFont
import re
from pathlib import Path


def _fallback_points(content: str) -> list[str]:
    """Simple fallback: extract bullet points from content."""
    points = []
    for raw in content.split("\n"):
        cleaned = re.sub(r"\*+", "", raw).strip()
        cleaned = re.sub(r"^[-•·]\s*", "", cleaned).strip()
        if cleaned:
            points.append(cleaned[:25] + "…" if len(cleaned) > 25 else cleaned)
    return points[:5]


# ── Dimensions ────────────────────────────────────────────
W, H = 1080, 1080
PAD = 80

# ── Gen Z Dark Gradient palette ───────────────────────────
# Vibrant & Block-based style — energetic, bold, social-media
C_BG    = (8,  10,  26)    # deep dark navy    #080A1A
C_BG2   = (22, 12,  50)    # deep purple end   #160C32
C_VIBE1 = (99,  102, 241)  # electric indigo   #6366F1
C_VIBE2 = (168,  85, 247)  # vibrant purple    #A855F7
C_VIBE3 = (236,  72, 153)  # hot pink          #EC4899
C_WHITE = (255, 255, 255)  # pure white (headline text)
C_LIGHT = (226, 232, 240)  # near-white (body text)  #E2E8F0
C_MUTED = (148, 163, 184)  # slate muted       #94A3B8
C_DIM   = (71,   85, 105)  # dark slate        #475569
C_CARD  = (16,   18,  42)  # card surface      #10122A

SECTION_ORDER = ["核心觀點", "提及標的", "關鍵數據", "投資機會", "風險提示", "個人行動建議"]

# ── Font sizes ────────────────────────────────────────────
FS_BRAND    = 30
FS_CHANNEL  = 38
FS_TITLE    = 66
FS_LABEL    = 38
FS_CONTENT  = 42
FS_FOOTER   = 28
FS_PROGRESS = 28


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Find a system font that supports CJK characters."""
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    print("[card_generator] Warning: No CJK font found, Chinese text may not render correctly.")
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Wrap text (character-by-character for CJK) to fit max_width."""
    lines = []
    for raw_line in text.split("\n"):
        paragraph = re.sub(r"^[-*•·]\s*", "", raw_line.strip())
        if not paragraph:
            continue
        current = ""
        for char in paragraph:
            test = current + char
            if draw.textlength(test, font=font) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


def _draw_gradient_bg(draw: ImageDraw.ImageDraw) -> None:
    """Draw a top-to-bottom dark gradient background."""
    for gy in range(H):
        t = gy / H
        r = int(C_BG[0] + (C_BG2[0] - C_BG[0]) * t)
        g = int(C_BG[1] + (C_BG2[1] - C_BG[1]) * t)
        b = int(C_BG[2] + (C_BG2[2] - C_BG[2]) * t)
        draw.line([(0, gy), (W, gy)], fill=(r, g, b))


def _draw_top_strip(draw: ImageDraw.ImageDraw, height: int = 7) -> None:
    """Draw the tri-color gradient strip at the top."""
    seg = W // 3
    draw.rectangle([0,       0, seg,     height], fill=C_VIBE1)
    draw.rectangle([seg,     0, seg * 2, height], fill=C_VIBE2)
    draw.rectangle([seg * 2, 0, W,       height], fill=C_VIBE3)


def _draw_gradient_line(draw: ImageDraw.ImageDraw, y: int, x1: int = PAD, x2: int = W - PAD, h: int = 2) -> None:
    """Draw a horizontal tri-color gradient line."""
    seg = (x2 - x1) // 3
    draw.rectangle([x1,        y, x1 + seg,     y + h], fill=C_VIBE1)
    draw.rectangle([x1 + seg,  y, x1 + seg * 2, y + h], fill=C_VIBE2)
    draw.rectangle([x1 + seg * 2, y, x2,         y + h], fill=C_VIBE3)


def _make_title_card(title: str, channel: str, output_path: Path) -> Path:
    img = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)

    _draw_gradient_bg(draw)
    _draw_top_strip(draw)

    # Brand label
    font_brand = _load_font(FS_BRAND)
    draw.text((PAD, 46), "Investment Digest", font=font_brand, fill=C_MUTED)

    # Channel name — vibrant indigo
    font_channel = _load_font(FS_CHANNEL)
    draw.text((PAD, 96), channel, font=font_channel, fill=C_VIBE1)

    # Video title — centered vertically, large bold white
    font_title = _load_font(FS_TITLE)
    content_w = W - PAD * 2
    lines = _wrap_text(title, font_title, content_w, draw)
    line_h = FS_TITLE + 24
    y = H // 2 - (len(lines) * line_h) // 2
    for line in lines:
        draw.text((PAD, y), line, font=font_title, fill=C_WHITE)
        y += line_h

    # Gradient accent bar below title
    _draw_gradient_line(draw, y + 32, PAD, PAD + 180, h=5)

    # Bottom label
    font_bottom = _load_font(FS_FOOTER)
    draw.text((PAD, H - 96), "AI 投資摘要", font=font_bottom, fill=C_DIM)

    img.save(output_path)
    return output_path


def _make_section_card(
    section_title: str,
    points: list[str],
    index: int,
    total: int,
    video_title: str,
    channel_name: str,
    output_path: Path,
) -> Path:
    img = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)

    # ── Background ───────────────────────────────────────
    _draw_gradient_bg(draw)

    # ── Top tri-color strip ──────────────────────────────
    _draw_top_strip(draw, height=7)

    # ── Header: channel · EP ─────────────────────────────
    ep_match = re.search(r'EP\d+', video_title, re.IGNORECASE)
    ep_text = ep_match.group(0).upper() if ep_match else video_title[:10]
    header_text = f"{channel_name}  ·  {ep_text}"
    font_header = _load_font(FS_BRAND)
    draw.text((PAD, 26), header_text, font=font_header, fill=C_MUTED)

    # ── Progress pill (top-right) ─────────────────────────
    font_prog = _load_font(FS_PROGRESS)
    progress_text = f"{index} / {total}"
    prog_w = int(draw.textlength(progress_text, font=font_prog))
    pill_x1 = W - PAD - prog_w - 22
    pill_y1 = 18
    pill_x2 = W - PAD + 2
    pill_y2 = 62
    draw.rounded_rectangle([pill_x1, pill_y1, pill_x2, pill_y2], radius=20, fill=C_CARD)
    draw.text((pill_x1 + 11, 25), progress_text, font=font_prog, fill=C_MUTED)

    # ── Section label pill (vibrant indigo) ──────────────
    font_label = _load_font(FS_LABEL)
    label_w = int(draw.textlength(section_title, font=font_label)) + 52
    draw.rounded_rectangle([PAD, 90, PAD + label_w, 152], radius=31, fill=C_VIBE1)
    draw.text((PAD + 26, 101), section_title, font=font_label, fill=C_WHITE)

    # ── Gradient divider line ────────────────────────────
    _draw_gradient_line(draw, y=170, x1=PAD, x2=W - PAD, h=2)

    # ── Bullet list ──────────────────────────────────────
    font_content = _load_font(FS_CONTENT)
    text_max_w = W - PAD * 2 - 58   # leave room for bullet
    text_x = PAD + 52
    line_h = FS_CONTENT + 22
    y = 200

    for pt in points:
        wrapped = _wrap_text(pt, font_content, text_max_w, draw)

        # Filled circle bullet (center-aligned with first text line)
        dot_r = 9
        dot_cx = PAD + 16
        dot_cy = y + FS_CONTENT // 2
        draw.ellipse(
            [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
            fill=C_VIBE2,
        )

        # First line — pure white
        draw.text((text_x, y), wrapped[0] if wrapped else pt, font=font_content, fill=C_WHITE)
        y += line_h

        # Continuation lines — slightly muted white
        for cont in wrapped[1:]:
            draw.text((text_x, y), cont, font=font_content, fill=C_LIGHT)
            y += line_h

        y += 10  # gap between points

    # ── Footer ───────────────────────────────────────────
    # Short indigo accent bar
    draw.rectangle([PAD, H - 108, PAD + 56, H - 105], fill=C_VIBE1)

    font_footer = _load_font(FS_FOOTER)
    footer_text = video_title if len(video_title) <= 34 else video_title[:33] + "…"
    draw.text((PAD, H - 88), footer_text, font=font_footer, fill=C_DIM)

    img.save(output_path)
    return output_path


def parse_summary(md_path: Path) -> dict:
    """Extract title, channel, and sections from summary markdown."""
    text = md_path.read_text(encoding="utf-8")

    # Remove YAML frontmatter
    text = re.sub(r"^---.*?---\s*\n", "", text, flags=re.DOTALL)

    # Title (first # heading)
    title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "投資摘要"

    # Remove markdown links  [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Extract ## sections (standard markdown format)
    sections: dict[str, str] = {}
    for m in re.finditer(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if val:
            sections[key] = val

    # Fallback: detect plain-text section headers (e.g., when ## was stripped by
    # browser innerText rendering — Claude.ai renders ## headings as <h2> HTML,
    # so innerText returns the section name without the ## prefix)
    if not sections:
        known = set(SECTION_ORDER)
        current_section: str | None = None
        current_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped in known:
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = stripped
                current_lines = []
            elif current_section is not None:
                current_lines.append(line)
        if current_section and current_lines:
            sections[current_section] = "\n".join(current_lines).strip()

    return {"title": title, "sections": sections}


def generate_cards(md_path: Path, channel_name: str, output_dir: Path) -> list[Path]:
    """
    Generate all PNG cards for a summary file.

    Returns list of card paths in order (section cards only).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    data = parse_summary(md_path)
    title = data["title"]
    sections = data["sections"]

    cards: list[Path] = []

    # Section cards only (no title card), all 6 sections in fixed order
    ordered = [(k, sections[k]) for k in SECTION_ORDER if k in sections]
    if not ordered:
        return cards

    # Generate all bullet points in one Claude browser session
    print(f"  [card] 用 Claude 批次生成 {len(ordered)} 個章節的金句...")
    from backend.claude_browser import generate_card_points
    sections_dict = {title: content for title, content in ordered}
    all_points = generate_card_points(sections_dict)

    for i, (section_title, content) in enumerate(ordered, start=1):
        points = all_points.get(section_title) or _fallback_points(content)
        card_path = output_dir / f"card_{i:02d}.png"
        _make_section_card(section_title, points, i, len(ordered), title, channel_name, card_path)
        cards.append(card_path)

    return cards
