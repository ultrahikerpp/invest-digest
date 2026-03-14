"""
Generate 1080x1920 (9:16) image cards optimised for YouTube Shorts / TikTok.

Layout per video:
  card_00_hook.png      — Hook card:  one punchy question / insight
  card_01.png … card_N  — Section cards: 2-3 large bullet points each
  card_XX_cta.png       — CTA card:  follow / subscribe prompt
"""
from PIL import Image, ImageDraw, ImageFont
import re
from pathlib import Path


# ── Dimensions (9:16 vertical for Shorts) ─────────────────
W, H = 1080, 1920
PAD = 80

# ── Colour palette ─────────────────────────────────────────
C_BG    = (8,  10,  26)
C_BG2   = (22, 12,  50)
C_VIBE1 = (99,  102, 241)
C_VIBE2 = (168,  85, 247)
C_VIBE3 = (236,  72, 153)
C_WHITE = (255, 255, 255)
C_LIGHT = (226, 232, 240)
C_MUTED = (148, 163, 184)
C_DIM   = (71,   85, 105)
C_CARD  = (16,   18,  42)

# ── Font sizes (larger than square version) ────────────────
FS_BRAND     = 32
FS_CHANNEL   = 54
FS_HOOK      = 72
FS_LABEL     = 46
FS_CONTENT   = 52
FS_FOOTER    = 34
FS_PROGRESS  = 32
FS_CTA_TITLE = 52
FS_CTA_MAIN  = 82
FS_CTA_SUB   = 46


# ── Font loader ───────────────────────────────────────────
def _load_font(size: int) -> ImageFont.FreeTypeFont:
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
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Wrap text character-by-character for CJK."""
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


# ── Shared drawing helpers ────────────────────────────────

def _draw_gradient_bg(draw: ImageDraw.ImageDraw) -> None:
    for gy in range(H):
        t = gy / H
        r = int(C_BG[0] + (C_BG2[0] - C_BG[0]) * t)
        g = int(C_BG[1] + (C_BG2[1] - C_BG[1]) * t)
        b = int(C_BG[2] + (C_BG2[2] - C_BG[2]) * t)
        draw.line([(0, gy), (W, gy)], fill=(r, g, b))


def _draw_top_strip(draw: ImageDraw.ImageDraw, height: int = 9) -> None:
    seg = W // 3
    draw.rectangle([0,       0, seg,     height], fill=C_VIBE1)
    draw.rectangle([seg,     0, seg * 2, height], fill=C_VIBE2)
    draw.rectangle([seg * 2, 0, W,       height], fill=C_VIBE3)


def _draw_gradient_line(draw: ImageDraw.ImageDraw, y: int, x1: int = PAD, x2: int = W - PAD, h: int = 3) -> None:
    seg = (x2 - x1) // 3
    draw.rectangle([x1,           y, x1 + seg,     y + h], fill=C_VIBE1)
    draw.rectangle([x1 + seg,     y, x1 + seg * 2, y + h], fill=C_VIBE2)
    draw.rectangle([x1 + seg * 2, y, x2,           y + h], fill=C_VIBE3)


# ── Hook card ─────────────────────────────────────────────

def _make_hook_card(hook_text: str, title: str, channel: str, output_path: Path) -> Path:
    """
    First card with a provocative hook sentence.
    Large text centered vertically; channel name and episode at top.
    """
    img = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw)
    _draw_top_strip(draw)

    # Brand label
    font_brand = _load_font(FS_BRAND)
    draw.text((PAD, 48), "Investment Digest", font=font_brand, fill=C_MUTED)

    # Channel name — vibrant indigo
    font_channel = _load_font(FS_CHANNEL)
    draw.text((PAD, 96), channel, font=font_channel, fill=C_VIBE1)

    # Gradient divider below channel
    _draw_gradient_line(draw, y=174, x1=PAD, x2=W - PAD)

    # Hook text — large, vertically centred between 300 and 1700
    font_hook = _load_font(FS_HOOK)
    content_w = W - PAD * 2
    lines = _wrap_text(hook_text, font_hook, content_w, draw)
    line_h = FS_HOOK + 30
    total_h = len(lines) * line_h
    y = max(300, 950 - total_h // 2)
    for line in lines:
        draw.text((PAD, y), line, font=font_hook, fill=C_WHITE)
        y += line_h

    # Accent bar below hook text
    _draw_gradient_line(draw, y + 50, PAD, PAD + 220, h=6)

    # "展開看更多 ↓" hint — centred near bottom
    font_footer = _load_font(FS_FOOTER)
    hint = "展開看更多 ↓"
    hint_w = int(draw.textlength(hint, font=font_footer))
    draw.text(((W - hint_w) // 2, H - 150), hint, font=font_footer, fill=C_MUTED)

    # Episode tag bottom-left
    ep_match = re.search(r'EP\d+', title, re.IGNORECASE)
    if ep_match:
        ep_text = ep_match.group(0).upper()
        font_ep = _load_font(FS_BRAND)
        draw.text((PAD, H - 90), ep_text, font=font_ep, fill=C_DIM)

    img.save(output_path)
    return output_path


# ── Section card (Shorts version) ────────────────────────

def _make_section_card_shorts(
    section_title: str,
    points: list[str],
    index: int,
    total: int,
    video_title: str,
    channel_name: str,
    output_path: Path,
) -> Path:
    """
    Section card: 2-3 large bullet points on a 1080×1920 canvas.
    Points are vertically centred for visual balance.
    """
    img = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw)
    _draw_top_strip(draw)

    # ── Header: channel · EP ──────────────────────────────
    ep_match = re.search(r'EP\d+', video_title, re.IGNORECASE)
    ep_text = ep_match.group(0).upper() if ep_match else video_title[:10]
    header_text = f"{channel_name}  ·  {ep_text}"
    font_header = _load_font(FS_BRAND)
    draw.text((PAD, 28), header_text, font=font_header, fill=C_MUTED)

    # ── Progress pill (top-right) ─────────────────────────
    font_prog = _load_font(FS_PROGRESS)
    progress_text = f"{index} / {total}"
    prog_w = int(draw.textlength(progress_text, font=font_prog))
    pill_x1 = W - PAD - prog_w - 24
    pill_x2 = W - PAD + 4
    draw.rounded_rectangle([pill_x1, 18, pill_x2, 70], radius=24, fill=C_CARD)
    draw.text((pill_x1 + 12, 28), progress_text, font=font_prog, fill=C_MUTED)

    # ── Section label pill ────────────────────────────────
    font_label = _load_font(FS_LABEL)
    label_w = int(draw.textlength(section_title, font=font_label)) + 64
    draw.rounded_rectangle([PAD, 90, PAD + label_w, 164], radius=38, fill=C_VIBE1)
    draw.text((PAD + 32, 106), section_title, font=font_label, fill=C_WHITE)

    # ── Gradient divider ──────────────────────────────────
    _draw_gradient_line(draw, y=188, x1=PAD, x2=W - PAD, h=3)

    # ── Bullet points — vertically centred ───────────────
    font_content = _load_font(FS_CONTENT)
    text_max_w = W - PAD * 2 - 74
    text_x = PAD + 68
    line_h = FS_CONTENT + 22
    bullet_gap = 36   # extra gap between bullet points

    capped = points[:5]   # Shorts: max 5 bullets

    # Pre-wrap all points to know total height
    all_wrapped = [_wrap_text(pt, font_content, text_max_w, draw) or [pt] for pt in capped]
    total_text_h = (
        sum(len(w) * line_h for w in all_wrapped)
        + (len(capped) - 1) * bullet_gap
    )

    content_top = 240
    content_bottom = H - 160
    available = content_bottom - content_top
    y = content_top + max(0, (available - total_text_h) // 2)

    for wrapped in all_wrapped:
        # Filled circle bullet aligned with first text line
        dot_r = 13
        dot_cx = PAD + 24
        dot_cy = y + FS_CONTENT // 2
        draw.ellipse(
            [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
            fill=C_VIBE2,
        )
        # First line — pure white
        draw.text((text_x, y), wrapped[0], font=font_content, fill=C_WHITE)
        y += line_h
        # Continuation lines — muted white
        for cont in wrapped[1:]:
            draw.text((text_x, y), cont, font=font_content, fill=C_LIGHT)
            y += line_h
        y += bullet_gap

    # ── Footer ────────────────────────────────────────────
    _draw_gradient_line(draw, y=H - 126, x1=PAD, x2=W - PAD, h=2)
    font_footer = _load_font(FS_FOOTER)
    footer_text = video_title if len(video_title) <= 28 else video_title[:27] + "…"
    draw.text((PAD, H - 100), footer_text, font=font_footer, fill=C_DIM)

    img.save(output_path)
    return output_path


# ── CTA card ──────────────────────────────────────────────

def _make_cta_card(channel: str, hashtags: str, output_path: Path) -> Path:
    """
    Last card: call-to-action to follow the channel.
    """
    img = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw)
    _draw_top_strip(draw)

    # Brand label
    font_brand = _load_font(FS_BRAND)
    draw.text((PAD, 48), "Investment Digest", font=font_brand, fill=C_MUTED)

    # Gradient divider
    _draw_gradient_line(draw, y=112, x1=PAD, x2=W - PAD)

    # "喜歡這集？"
    font_label = _load_font(FS_CTA_TITLE)
    draw.text((PAD, 168), "喜歡這集？", font=font_label, fill=C_MUTED)

    # Large CTA: "追蹤頻道 🔔" + brand name — centred
    font_cta = _load_font(FS_CTA_MAIN)
    cta_lines = ["追蹤頻道 🔔", "Ultra Invest Digest"]
    line_h_cta = FS_CTA_MAIN + 36
    total_cta_h = len(cta_lines) * line_h_cta
    y = 820 - total_cta_h // 2

    for line in cta_lines:
        line_w = int(draw.textlength(line, font=font_cta))
        x = max(PAD, (W - line_w) // 2)
        draw.text((x, y), line, font=font_cta, fill=C_WHITE)
        y += line_h_cta

    # Gradient accent below CTA
    _draw_gradient_line(draw, y + 50, PAD + 100, W - PAD - 100, h=6)

    # Subtext
    font_sub = _load_font(FS_CTA_SUB)
    sub_text = "每週投資重點不漏接"
    sub_w = int(draw.textlength(sub_text, font=font_sub))
    draw.text(((W - sub_w) // 2, y + 110), sub_text, font=font_sub, fill=C_LIGHT)

    # Hashtags at the bottom (first 3 only)
    if hashtags:
        tags = hashtags.split()[:3]
        tags_text = " ".join(tags)
        font_tags = _load_font(FS_BRAND)
        draw.text((PAD, H - 120), tags_text, font=font_tags, fill=C_DIM)

    img.save(output_path)
    return output_path


# ── Public API ────────────────────────────────────────────

def generate_cards_shorts(
    md_path: Path,
    channel_name: str,
    output_dir: Path,
    hashtags: str = "",
) -> list[Path]:
    """
    Generate Shorts-optimised PNG cards (1080×1920, 9:16).

    Returns list of card paths in order:
      [hook_card, section_card×N, cta_card]
    """
    from backend.card_generator import parse_summary, SECTION_ORDER, _fallback_points
    from backend.claude_browser import generate_card_points_shorts

    output_dir.mkdir(parents=True, exist_ok=True)

    data = parse_summary(md_path)
    title = data["title"]
    sections = data["sections"]

    ordered = [(k, sections[k]) for k in SECTION_ORDER if k in sections]
    if not ordered:
        return []

    total_section_cards = len(ordered)

    # Generate Shorts bullet points + hook via Claude
    print(f"  [shorts] 用 Claude 批次生成 Shorts 金句 + Hook...")
    sections_dict = {t: c for t, c in ordered}
    all_points, hook_text = generate_card_points_shorts(sections_dict)

    cards: list[Path] = []

    # 1. Hook card (card_00)
    hook_path = output_dir / "card_00_hook.png"
    _make_hook_card(hook_text or title, title, channel_name, hook_path)
    cards.append(hook_path)
    print(f"  [shorts] ✓ Hook 卡片")

    # 2. Section cards (card_01 … card_N)
    for i, (section_title, content) in enumerate(ordered, start=1):
        points = all_points.get(section_title) or _fallback_points(content)
        points = [p for p in points if p][:5]
        card_path = output_dir / f"card_{i:02d}.png"
        _make_section_card_shorts(
            section_title, points, i, total_section_cards,
            title, channel_name, card_path
        )
        cards.append(card_path)
        print(f"  [shorts] ✓ {section_title} ({len(points)} 條)")

    # 3. CTA card (card_N+1)
    cta_path = output_dir / f"card_{total_section_cards + 1:02d}_cta.png"
    _make_cta_card(channel_name, hashtags, cta_path)
    cards.append(cta_path)
    print(f"  [shorts] ✓ CTA 卡片")

    return cards
