"""
Read session cookies from the Chrome profile signed in as CHROME_PROFILE_EMAIL.

browser_cookie3.chrome() without `cookie_file` silently picks the first
profile it finds (usually `Default`), which may belong to a different Google
account than the one logged in to claude.ai / chatgpt.com.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PROFILE_EMAIL_ENV = "CHROME_PROFILE_EMAIL"
CHROME_USER_DATA_DIR = Path.home() / "Library/Application Support/Google/Chrome"
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _profile_email() -> str | None:
    """CHROME_PROFILE_EMAIL from the environment, falling back to .env."""
    value = os.environ.get(PROFILE_EMAIL_ENV)
    if value is None and _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            key, sep, raw = line.strip().partition("=")
            if sep and key.strip() == PROFILE_EMAIL_ENV:
                value = raw.strip().strip('"').strip("'")
                break
    if not value or not value.strip():
        return None
    return value.strip()


def resolve_cookie_file(email: str, user_data_dir: Path | None = None) -> str:
    """Return the Cookies DB path of the Chrome profile signed in as `email`."""
    user_data_dir = user_data_dir or CHROME_USER_DATA_DIR
    local_state = json.loads((user_data_dir / "Local State").read_text(encoding="utf-8"))
    profiles = local_state.get("profile", {}).get("info_cache", {})
    for profile_dir, info in profiles.items():
        if (info.get("user_name") or "").lower() == email.lower():
            for candidate in ("Cookies", "Network/Cookies"):
                path = user_data_dir / profile_dir / candidate
                if path.exists():
                    return str(path)
            raise RuntimeError(f"Chrome 設定檔「{profile_dir}」({email}) 找不到 Cookies 檔")
    known = ", ".join(sorted(i.get("user_name") or "?" for i in profiles.values()))
    raise RuntimeError(
        f"找不到以 {email} 登入的 Chrome 設定檔（{PROFILE_EMAIL_ENV}）。現有帳號：{known}"
    )


def load_chrome_cookies(domain: str) -> list[dict]:
    """Cookies for `domain` from the configured Chrome profile, in Playwright format."""
    import browser_cookie3

    email = _profile_email()
    cookie_file = resolve_cookie_file(email) if email else None
    return [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path or "/",
            "secure": bool(c.secure),
            "httpOnly": False,
            "sameSite": "Lax",
        }
        for c in browser_cookie3.chrome(cookie_file=cookie_file, domain_name=domain)
    ]
