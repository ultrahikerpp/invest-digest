#!/usr/bin/env python3
"""
Subscriber management backed by Supabase.

All read/write operations use the SERVICE_KEY (server-side only).
The ANON_KEY is only written to docs/data/subscribe_config.json for browser use.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def _read_env(key: str) -> str:
    from backend.worker import _read_env_value
    return _read_env_value(key)


def _headers() -> dict:
    key = _read_env("SUPABASE_SERVICE_KEY")
    if not key or not key.startswith("ey"):
        raise RuntimeError("SUPABASE_SERVICE_KEY not set in .env — subscriber features disabled")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    base = _read_env("SUPABASE_URL").rstrip("/")
    if not base:
        raise RuntimeError("SUPABASE_URL not set in .env — subscriber features disabled")
    return f"{base}{path}"


def _site_base() -> str:
    return _read_env("SITE_BASE_URL").rstrip("/") or "https://yocoppp.github.io/investment-digest"


# ── Supabase queries ──────────────────────────────────────

def get_pending_confirmation() -> list[dict]:
    """Subscribers not yet sent a confirmation email."""
    import httpx
    resp = httpx.get(
        _url("/rest/v1/subscribers"),
        headers=_headers(),
        params={"confirmed": "eq.false", "confirm_sent_at": "is.null", "select": "*"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def mark_confirmation_sent(subscriber_id: str) -> None:
    import httpx
    now = datetime.now(timezone.utc).isoformat()
    resp = httpx.patch(
        _url("/rest/v1/subscribers"),
        headers=_headers(),
        params={"id": f"eq.{subscriber_id}"},
        json={"confirm_sent_at": now},
        timeout=15,
    )
    resp.raise_for_status()


def get_confirmed_subscribers(channel_id: str) -> list[dict]:
    """Confirmed subscribers who opted into the given channel_id."""
    import httpx
    resp = httpx.get(
        _url("/rest/v1/subscribers"),
        headers=_headers(),
        params={
            "confirmed": "eq.true",
            "channels": f"cs.{{{channel_id}}}",
            "select": "email,unsubscribe_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_weekly_digest_subscribers() -> list[dict]:
    """Confirmed subscribers who opted into the weekly digest."""
    import httpx
    resp = httpx.get(
        _url("/rest/v1/subscribers"),
        headers=_headers(),
        params={
            "confirmed": "eq.true",
            "weekly_digest": "eq.true",
            "select": "email,unsubscribe_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Email sending ─────────────────────────────────────────

def _excerpt(summary_path) -> str:
    """Extract first ~200 chars of plain text from a markdown summary."""
    if not summary_path:
        return ""
    p = Path(summary_path)
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    # Strip frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        content = content[end + 3:].lstrip("\n") if end != -1 else content
    # Strip markdown: remove headings, emoji-link lines (🔗), links, bold, etc.
    content = re.sub(r'^🔗.+$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^#{1,6}\s+', '', content, flags=re.MULTILINE)
    content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)
    content = re.sub(r'[*_`]', '', content)
    content = re.sub(r'\n{2,}', '\n', content).strip()
    return content[:220] + "…" if len(content) > 220 else content


def send_confirmation_email(email: str, confirm_token: str) -> None:
    from backend.worker import send_html_email
    site = _site_base()
    confirm_url = f"{site}/#/confirm?token={confirm_token}"
    subject = "請確認您訂閱《投資文摘》"
    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#131722;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#131722;padding:40px 20px;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0"
  style="background:#1E222D;border-radius:12px;overflow:hidden;max-width:560px;width:100%;">
  <tr><td style="background:linear-gradient(135deg,#1565C0,#2962FF);padding:32px 40px;">
    <div style="font-size:22px;font-weight:700;color:#fff;">Ultra Investment Digest</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.75);margin-top:4px;">財經投資頻道重點摘要</div>
  </td></tr>
  <tr><td style="padding:36px 40px;">
    <p style="margin:0 0 16px;font-size:16px;color:#D1D4DC;">感謝您訂閱！</p>
    <p style="margin:0 0 28px;font-size:14px;color:#9598A1;line-height:1.7;">
      請點擊下方按鈕確認您的訂閱，即可開始收到最新節目通知。
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{confirm_url}"
        style="display:inline-block;background:#2962FF;color:#fff;font-size:15px;
               font-weight:600;padding:14px 36px;border-radius:8px;text-decoration:none;">
        確認訂閱
      </a>
    </div>
    <p style="margin:28px 0 0;font-size:12px;color:#6B7280;line-height:1.6;">
      若您並未訂閱，請忽略此郵件。
    </p>
  </td></tr>
  <tr><td style="background:#181D2E;padding:16px 40px;border-top:1px solid rgba(255,255,255,0.06);">
    <p style="margin:0;font-size:12px;color:#6B7280;">Ultra Investment Digest</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    send_html_email(subject, html, email)


def send_episode_notification(email: str, unsubscribe_token: str, episode: dict) -> None:
    from backend.worker import send_html_email
    site = _site_base()
    unsub_url = f"{site}/#/unsubscribe?token={unsubscribe_token}"
    channel_name = episode.get("channel_name", "")
    title = episode.get("title", "")
    video_id = episode.get("video_id", "")
    excerpt = episode.get("summary_excerpt", "")
    source_type = episode.get("source_type", "youtube")

    if source_type == "newsletter":
        watch_btn = ""
    else:
        watch_url = f"https://youtube.com/watch?v={video_id}"
        watch_btn = (
            f'<a href="{watch_url}" style="display:inline-block;background:rgba(41,98,255,0.14);'
            f'color:#5C9EFF;font-size:14px;font-weight:600;padding:12px 24px;'
            f'border-radius:8px;text-decoration:none;">觀看影片</a>'
        )

    subject = f"[新節目] {channel_name}｜{title}"
    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#131722;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#131722;padding:40px 20px;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0"
  style="background:#1E222D;border-radius:12px;overflow:hidden;max-width:560px;width:100%;">
  <tr><td style="background:linear-gradient(135deg,#1565C0,#2962FF);padding:28px 40px;">
    <div style="font-size:12px;color:rgba(255,255,255,0.7);margin-bottom:6px;
                text-transform:uppercase;letter-spacing:0.06em;">{channel_name} · 新節目</div>
    <div style="font-size:20px;font-weight:700;color:#fff;line-height:1.4;">{title}</div>
  </td></tr>
  <tr><td style="padding:28px 40px;">
    <p style="margin:0 0 24px;font-size:14px;color:#9598A1;line-height:1.8;">{excerpt}</p>
    <div style="display:flex;gap:12px;justify-content:center;margin:24px 0;
                text-align:center;flex-wrap:wrap;">
      <a href="{site}/#/episode/{video_id}" style="display:inline-block;background:#2962FF;color:#fff;
         font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;
         text-decoration:none;margin:4px;">閱讀完整摘要</a>
      {watch_btn}
    </div>
  </td></tr>
  <tr><td style="background:#181D2E;padding:16px 40px;border-top:1px solid rgba(255,255,255,0.06);">
    <p style="margin:0;font-size:12px;color:#6B7280;">
      Ultra Investment Digest ·
      <a href="{unsub_url}" style="color:#6B7280;text-decoration:underline;">退訂</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    send_html_email(subject, html, email)


def send_weekly_digest(email: str, unsubscribe_token: str, episodes: list[dict], week_label: str) -> None:
    from backend.worker import send_html_email
    from collections import defaultdict
    site = _site_base()
    unsub_url = f"{site}/#/unsubscribe?token={unsubscribe_token}"

    by_channel: dict[str, list] = defaultdict(list)
    for ep in episodes:
        by_channel[ep.get("channel_name", ep.get("channel_id", ""))].append(ep)

    episodes_html = ""
    for channel_name, eps in by_channel.items():
        episodes_html += (
            f'<div style="margin-bottom:28px;">'
            f'<div style="font-size:12px;font-weight:600;color:#5C9EFF;margin-bottom:10px;'
            f'text-transform:uppercase;letter-spacing:0.06em;">{channel_name}</div>'
        )
        for ep in eps:
            episodes_html += (
                f'<div style="margin-bottom:14px;padding:16px;background:#131722;'
                f'border-radius:8px;border-left:3px solid #2962FF;">'
                f'<div style="font-size:15px;font-weight:600;color:#D1D4DC;margin-bottom:8px;">'
                f'{ep.get("title", "")}</div>'
                f'<div style="font-size:13px;color:#9598A1;line-height:1.7;">'
                f'{ep.get("summary_excerpt", "")}</div>'
                f'</div>'
            )
        episodes_html += "</div>"

    subject = f"[投資週報] {week_label} 共 {len(episodes)} 集"
    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#131722;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#131722;padding:40px 20px;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0"
  style="background:#1E222D;border-radius:12px;overflow:hidden;max-width:560px;width:100%;">
  <tr><td style="background:linear-gradient(135deg,#1565C0,#2962FF);padding:28px 40px;">
    <div style="font-size:12px;color:rgba(255,255,255,0.7);margin-bottom:6px;
                text-transform:uppercase;letter-spacing:0.06em;">投資週報</div>
    <div style="font-size:22px;font-weight:700;color:#fff;">{week_label}</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.75);margin-top:6px;">
      共 {len(episodes)} 集節目摘要</div>
  </td></tr>
  <tr><td style="padding:28px 40px;">
    {episodes_html}
    <div style="text-align:center;margin:24px 0;">
      <a href="{site}/#/weekly"
        style="display:inline-block;background:#2962FF;color:#fff;font-size:14px;
               font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;">
        查看完整週報
      </a>
    </div>
  </td></tr>
  <tr><td style="background:#181D2E;padding:16px 40px;border-top:1px solid rgba(255,255,255,0.06);">
    <p style="margin:0;font-size:12px;color:#6B7280;">
      Ultra Investment Digest ·
      <a href="{unsub_url}" style="color:#6B7280;text-decoration:underline;">退訂</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    send_html_email(subject, html, email)
