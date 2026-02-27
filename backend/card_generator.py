"""
Generate 1080x1920 image cards from investment summary markdown files.
Each section becomes one card (9:16 vertical for YouTube Shorts / TikTok).
"""
from PIL import Image, ImageDraw, ImageFont
import re
from pathlib import Path

# Dimensions (9:16 vertical)
W, H = 1080, 1920
PAD = 90

# Color palette
C_BG     = (10, 14, 26)
C_CARD   = (18, 25, 45)
C_ACCENT = (52, 199, 142)
C_WHITE  = (245, 245, 250)
C_GRAY   = (160, 165, 180)
C_DIM    = (80, 88, 110)

SECTION_ORDER = ["核心觀點", "提及標的", "關鍵數據", "投資機會", "風險提示", "個人行動建議"]

# Font size constants
FS_BRAND   = 32
FS_CHANNEL = 38
FS_TITLE   = 68
FS_LABEL   = 36
FS_CONTENT = 46
FS_FOOTER  = 30
FS_PROGRESS = 30


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
        # Normalize bullet points
        paragraph = re.sub(r"^[-*•·]\s*", "• ", raw_line.strip())
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


def _make_title_card(title: str, channel: str, output_path: Path) -> Path:
    img = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)

    # Top accent bar
    draw.rectangle([0, 0, W, 8], fill=C_ACCENT)

    # Brand label
    font_brand = _load_font(FS_BRAND)
    draw.text((PAD, 55), "Investment Digest", font=font_brand, fill=C_ACCENT)

    # Channel name
    font_channel = _load_font(FS_CHANNEL)
    draw.text((PAD, 110), channel, font=font_channel, fill=C_GRAY)

    # Video title — centered vertically
    font_title = _load_font(FS_TITLE)
    content_w = W - PAD * 2
    lines = _wrap_text(title, font_title, content_w, draw)
    line_h = FS_TITLE + 22
    y = H // 2 - (len(lines) * line_h) // 2
    for line in lines:
        draw.text((PAD, y), line, font=font_title, fill=C_WHITE)
        y += line_h

    # Accent divider below title
    draw.rectangle([PAD, y + 36, PAD + 80, y + 44], fill=C_ACCENT)

    # Bottom label
    font_bottom = _load_font(FS_FOOTER)
    draw.text((PAD, H - 110), "AI 投資摘要", font=font_bottom, fill=C_DIM)

    img.save(output_path)
    return output_path


def _make_section_card(
    section_title: str,
    content: str,
    index: int,
    total: int,
    video_title: str,
    output_path: Path,
) -> Path:
    img = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)

    # Top accent bar
    draw.rectangle([0, 0, W, 8], fill=C_ACCENT)

    # Progress indicator (top-right)
    font_prog = _load_font(FS_PROGRESS)
    progress_text = f"{index} / {total}"
    prog_w = int(draw.textlength(progress_text, font=font_prog))
    draw.text((W - PAD - prog_w, 38), progress_text, font=font_prog, fill=C_DIM)

    # Section label pill (green badge)
    font_label = _load_font(FS_LABEL)
    label_w = int(draw.textlength(section_title, font=font_label)) + 52
    draw.rounded_rectangle([PAD, 95, PAD + label_w, 158], radius=32, fill=C_ACCENT)
    draw.text((PAD + 26, 106), section_title, font=font_label, fill=C_BG)

    # Divider
    draw.rectangle([PAD, 186, W - PAD, 189], fill=C_CARD)

    # Content
    font_content = _load_font(FS_CONTENT)
    content_w = W - PAD * 2
    lines = _wrap_text(content, font_content, content_w, draw)

    # Max lines before footer area
    max_lines = int((H - 280 - 160) / (FS_CONTENT + 18))
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + ["…"]

    y = 220
    line_h = FS_CONTENT + 18
    for line in lines:
        draw.text((PAD, y), line, font=font_content, fill=C_WHITE)
        y += line_h

    # Footer separator
    draw.rectangle([0, H - 130, W, H - 128], fill=C_DIM)

    # Footer: video title
    font_footer = _load_font(FS_FOOTER)
    footer_text = video_title if len(video_title) <= 32 else video_title[:31] + "…"
    draw.text((PAD, H - 100), footer_text, font=font_footer, fill=C_GRAY)

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

    # Extract ## sections
    sections: dict[str, str] = {}
    for m in re.finditer(r"^## (.+)\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if val:
            sections[key] = val

    return {"title": title, "sections": sections}


def generate_cards(md_path: Path, channel_name: str, output_dir: Path) -> list[Path]:
    """
    Generate all PNG cards for a summary file.

    Returns list of card paths in order (title card first, then sections).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    data = parse_summary(md_path)
    title = data["title"]
    sections = data["sections"]

    cards: list[Path] = []

    # Title card
    title_card = output_dir / "card_00.png"
    _make_title_card(title, channel_name, title_card)
    cards.append(title_card)

    # Section cards (in fixed order, skip missing sections)
    ordered = [(k, sections[k]) for k in SECTION_ORDER if k in sections]
    for i, (section_title, content) in enumerate(ordered, start=1):
        card_path = output_dir / f"card_{i:02d}.png"
        _make_section_card(section_title, content, i, len(ordered), title, card_path)
        cards.append(card_path)

    return cards
