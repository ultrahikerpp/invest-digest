#!/usr/bin/env python3
"""
Fetch FOMO研究院 free newsletters (KP思考筆記) from Gmail via IMAP.

Uses the same GMAIL_APP_PASSWORD from .env as the notification sender.
IMAP must be enabled in Gmail settings (Settings → See all settings → Forwarding
and POP/IMAP → Enable IMAP).
"""
from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import os
import re
from datetime import datetime
from pathlib import Path


GMAIL_USER = "yocoppp@gmail.com"
GMAIL_IMAP_HOST = "imap.gmail.com"


def _load_dotenv() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _get_app_password() -> str:
    _load_dotenv()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not pw:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD not set in .env\n"
            "  See: myaccount.google.com/apppasswords"
        )
    return pw


def _decode_header(raw: str) -> str:
    """Decode a potentially encoded email header value."""
    parts = email.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _parse_issue_number(subject: str) -> str | None:
    """Extract issue number from subject like '...KP思考筆記(第34期)'."""
    m = re.search(r"第(\d+)期", subject)
    return m.group(1) if m else None


def _extract_substack_url(body: str) -> str:
    """Extract the 'View this post on the web' Substack URL."""
    m = re.search(r"View this post on the web at (https://\S+)", body)
    return m.group(1) if m else ""


def _clean_body(raw_body: str) -> str:
    """Remove Substack boilerplate and clean up whitespace."""
    body = raw_body

    # Remove "View this post on the web at ..." header line
    body = re.sub(r"^View this post on the web at https?://\S+\r?\n\r?\n?", "", body)

    # Remove Substack subscription CTA banners
    body = re.sub(
        r"FOMO研究院電子報 is a reader-supported publication\..*?subscriber\.\r?\n",
        "",
        body,
    )

    # Remove unsubscribe footer and everything after it
    body = re.sub(r"\r?\nUnsubscribe https?://.*$", "", body, flags=re.DOTALL)

    # Collapse excessive blank lines
    body = re.sub(r"(\r?\n){3,}", "\n\n", body)

    return body.strip()


def _extract_plain_text(msg: email.message.Message) -> str:
    """Extract and clean plain text from an email message."""
    raw = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                try:
                    raw = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception:
                    continue
    else:
        charset = msg.get_content_charset() or "utf-8"
        raw = msg.get_payload(decode=True).decode(charset, errors="replace")

    return _clean_body(raw)


def fetch_newsletters(
    sender: str,
    subject_filter: str,
    max_results: int = 10,
) -> list[dict]:
    """
    Fetch free newsletters from Gmail via IMAP.

    Args:
        sender: Sender email address to filter on (e.g. 'fomosoc@substack.com').
        subject_filter: Regex pattern for the subject (e.g. 'KP思考筆記|深入分析').
        max_results: Maximum number of matching newsletters to return.

    Returns:
        List of dicts sorted newest-first:
          {video_id, title, published_at, body, substack_url, issue_number}
    """
    app_password = _get_app_password()

    mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST)
    try:
        mail.login(GMAIL_USER, app_password)
        mail.select("INBOX")

        # Search by sender; IMAP FROM search matches substring
        _, data = mail.search(None, f'FROM "{sender}"')
        msg_ids = data[0].split()
        if not msg_ids:
            return []

        # Process most recent first; limit how many we inspect to 3× max_results
        inspect_ids = msg_ids[-max_results * 5:]

        newsletters: list[dict] = []
        for msg_id in reversed(inspect_ids):
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_header(msg.get("Subject", ""))

            # Use regex to match subject
            if not re.search(subject_filter, subject):
                continue

            issue_num = _parse_issue_number(subject)
            if not issue_num:
                continue

            # Determine prefix based on series
            prefix = "kp-newsletter"
            if "深入分析" in subject:
                prefix = "fomo-analysis"

            # Parse send date
            date_str = msg.get("Date", "")
            try:
                dt = email.utils.parsedate_to_datetime(date_str)
                published_at = dt.strftime("%Y-%m-%d")
            except Exception:
                published_at = datetime.now().strftime("%Y-%m-%d")

            # Extract body before cleaning (need raw for URL extraction)
            raw_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            raw_body = part.get_payload(decode=True).decode(
                                charset, errors="replace"
                            )
                            break
                        except Exception:
                            continue
            else:
                charset = msg.get_content_charset() or "utf-8"
                raw_body = msg.get_payload(decode=True).decode(charset, errors="replace")

            substack_url = _extract_substack_url(raw_body)
            body = _clean_body(raw_body)

            if not body:
                continue

            newsletters.append(
                {
                    "video_id": f"{prefix}-{issue_num}",
                    "title": subject,
                    "published_at": published_at,
                    "body": body,
                    "substack_url": substack_url,
                    "issue_number": issue_num,
                }
            )

            if len(newsletters) >= max_results:
                break

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return newsletters
