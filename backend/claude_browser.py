#!/usr/bin/env python3
"""
Generate summaries/hashtags by automating Claude's web UI via Playwright.

Strategy: extract claude.ai session cookies directly from the user's Chrome
browser (no login step needed), inject them into a Playwright context, and
interact with the chat interface headlessly.

Prerequisites:
  1. Be logged in to claude.ai in Chrome at least once.
  2. On first run, macOS may prompt "python3 wants to access your keychain" —
     click Allow. This is needed to decrypt Chrome's cookie database.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

CLAUDE_NEW_CHAT_URL = "https://claude.ai/new"


# ── Prompt builders ───────────────────────────────────────

def _build_summary_prompt(transcript: str, title: str) -> str:
    return f"""你是一位專業的投資分析師助理。請分析以下投資 Podcast / YouTube 影片的逐字稿，產出結構化的投資重點摘要。

影片標題：{title}

逐字稿（含時間戳記）：
{transcript[:8000]}

【重要前置處理】
逐字稿開頭可能包含廣告或贊助商宣傳（通常在前 1-5 分鐘內），常見特徵包括：
- 介紹產品、平台、服務
- 邀請觀眾訂閱、使用優惠碼
- 宣傳自家課程、書籍、社群
- 說「今天的節目由 XX 贊助」等話術
請完全忽略這些廣告內容，只針對實質投資討論進行摘要。

請用繁體中文產出以下格式的 Markdown 摘要：

## 核心觀點
（3-5個主要投資觀點）

## 提及標的
（股票、ETF、產業、市場等，若無則標注「本集未提及具體標的」）

## 關鍵數據
（重要數字、指標、時間點）

## 投資機會
（值得關注的機會）

## 風險提示
（提到的風險或注意事項）

## 個人行動建議
（根據內容，投資人可以採取的具體行動）"""


def _build_hashtag_prompt(summary_body: str) -> str:
    return f"""根據以下投資摘要內容，產出 5 個最重要的關鍵字 hashtag。

摘要內容：
{summary_body[:3000]}

要求：
- 只輸出 5 個 hashtag，以空格分隔
- 每個 hashtag 以 # 開頭，不含空格
- 選擇最能代表本集投資重點的關鍵詞（如股票代號、產業、主題、觀點）
- 使用繁體中文或英文
- 直接輸出 hashtag，不要有任何其他說明文字

範例格式：#台積電 #AI #半導體 #投資機會 #美股"""


# ── Cookie extraction ─────────────────────────────────────

def _get_claude_cookies() -> list[dict]:
    """
    Extract claude.ai session cookies from the user's Chrome browser.
    macOS: Chrome encrypts cookies with a key stored in the system Keychain.
           On first run, macOS will ask 'python3 wants to access your keychain' — click Allow.
    """
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name="claude.ai")
        cookies = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path or "/",
                "secure": bool(c.secure),
                "httpOnly": False,
                "sameSite": "Lax",
            }
            for c in cj
        ]
        if not cookies:
            raise RuntimeError("未找到 claude.ai cookies")
        return cookies
    except ImportError:
        raise RuntimeError(
            "請安裝 browser-cookie3：pip install browser-cookie3"
        )
    except Exception as e:
        raise RuntimeError(
            f"無法從 Chrome 取得 claude.ai 登入狀態：{e}\n"
            "請確認：\n"
            "  1. Chrome 已安裝且曾登入過 claude.ai\n"
            "  2. 若 macOS 詢問 Keychain 存取權限，請點選「允許」"
        )


# ── Browser helpers ───────────────────────────────────────

def _extract_last_response(page) -> str:
    """Extract the last assistant message text from the Claude page."""
    return page.evaluate("""() => {
        // Primary: claude.ai uses div[class*="font-claude-response"] for response body
        let els = document.querySelectorAll('div[class*="font-claude-response"]');
        if (els.length) return els[els.length - 1].innerText.trim();

        // Fallback: paragraph-level response class
        els = document.querySelectorAll('p[class*="font-claude-response-body"]');
        if (els.length) {
            // Collect all paragraphs (in case of multi-paragraph response)
            return Array.from(els).map(el => el.innerText.trim()).join('\\n\\n');
        }

        return '';
    }""") or ""


def _wait_for_stable_response(page, timeout_secs: int = 180) -> str:
    """Poll until the response text stops changing for 3 consecutive seconds."""
    prev = ""
    stable_count = 0
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        current = _extract_last_response(page)
        if current and current == prev:
            stable_count += 1
            if stable_count >= 3:
                return current
        else:
            stable_count = 0
            prev = current
        time.sleep(1)
    return prev  # return whatever we have on timeout


def chat(prompt: str, timeout_secs: int = 180) -> str:
    """
    Inject Chrome cookies into a Playwright browser, open claude.ai/new,
    send `prompt`, and return Claude's response text.

    No login step needed — cookies are read from the user's Chrome browser.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    # Extract login session from Chrome
    cookies = _get_claude_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,   # headless=True after confirmed working
            args=["--no-first-run"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        ctx.add_cookies(cookies)

        try:
            page = ctx.new_page()
            page.goto(CLAUDE_NEW_CHAT_URL, wait_until="domcontentloaded", timeout=60000)

            # ── Verify session is valid ───────────────────
            print("  [claude] 等待介面載入...", end="", flush=True)
            try:
                page.wait_for_selector('[contenteditable="true"]', timeout=15000)
                print(" 完成")
            except PWTimeout:
                raise RuntimeError(
                    "Claude 登入狀態已過期。請在 Chrome 中重新登入 claude.ai，"
                    "然後重新執行 runner.py"
                )

            # ── Input prompt ──────────────────────────────
            input_el = page.locator('[contenteditable="true"]').first
            input_el.click()

            # execCommand is reliable for React contenteditable
            page.evaluate(
                "(text) => document.execCommand('insertText', false, text)",
                prompt,
            )
            time.sleep(0.4)

            # ── Submit ────────────────────────────────────
            page.keyboard.press("Enter")
            print("  [claude] 傳送完成，等待回應...", end="", flush=True)

            # ── Wait for generation to complete ───────────
            # Strategy A: "Stop response" button appears → disappears
            stop_appeared = False
            try:
                page.wait_for_selector(
                    'button[aria-label="Stop response"]',
                    timeout=12000,
                )
                stop_appeared = True
                page.wait_for_selector(
                    'button[aria-label="Stop response"]',
                    state="hidden",
                    timeout=timeout_secs * 1000,
                )
            except PWTimeout:
                if not stop_appeared:
                    pass  # fall through to stability check

            # Strategy B: stability check (handles edge cases)
            time.sleep(1)
            response = _wait_for_stable_response(page, timeout_secs=30)
            print(" 完成")

            if not response:
                raise RuntimeError("無法擷取回應內容，請確認 claude.ai 已正常回應")

            return response

        finally:
            ctx.close()
            browser.close()


# ── Public API ────────────────────────────────────────────

def generate_summary(transcript: str, title: str) -> str:
    """Generate investment summary via Claude browser automation."""
    prompt = _build_summary_prompt(transcript, title)
    try:
        return chat(prompt, timeout_secs=180)
    except Exception as e:
        return (
            f"# {title}\n\n"
            f"⚠️ Claude 瀏覽器摘要失敗：{e}\n\n"
            f"## 逐字稿前段\n\n{transcript[:1000]}"
        )


def generate_hashtags(summary_body: str, channel_name: str) -> str:
    """Generate 5 keyword hashtags via Claude browser automation."""
    channel_tag = "#" + re.sub(r'\s+', '', channel_name)
    prompt = _build_hashtag_prompt(summary_body)
    try:
        raw = chat(prompt, timeout_secs=30)
        tags = [t if t.startswith("#") else f"#{t}" for t in raw.split() if t][:5]
        tags.append(channel_tag)
        return " ".join(tags)
    except Exception:
        return f"#投資 #財經 #重點摘要 #市場分析 #股市 {channel_tag}"


def generate_card_points(sections: dict[str, str]) -> dict[str, list[str]]:
    """
    Given a dict of {section_title: content}, return {section_title: [5 bullet points]}.
    All sections are processed in a single browser session (one chat call).
    """
    section_names = list(sections.keys())

    # Build batch prompt
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = f"""你是投資內容精華整理編輯。我有以下幾個投資摘要章節，請對每個章節各整理出 5 條重點金句。

嚴格要求：
- 每條金句必須是完整的一句話，有清楚的主詞與結論
- 每條金句長度必須剛好在 20 到 30 個繁體中文字之間（只計算中文字數，不計標點）
- 如果超過 30 字，請縮短；如果不足 20 字，請補充完整
- 偏向精闢、直接、有觀點的金句陳述
- 不加任何前綴符號（不要加 1. 或 • 或 - 或空格）
- 每個章節輸出 5 行金句，每行一條

請嚴格按照以下格式輸出（保留方括號標記，每組之間空一行）：

[章節名稱]
金句1
金句2
金句3
金句4
金句5

章節內容如下：

{sections_text}"""

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [claude] 批次金句生成失敗：{e}")
        return {name: [] for name in section_names}

    # Parse response: split on [章節名稱] markers
    result: dict[str, list[str]] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in raw.splitlines():
        line = line.strip()
        # Detect [章節名稱] header
        header_match = re.match(r'^\[(.+)\]$', line)
        if header_match:
            if current_name is not None:
                result[current_name] = current_lines[:5]
            current_name = header_match.group(1).strip()
            current_lines = []
        elif current_name is not None and line:
            # Strip any leading list markers just in case
            cleaned = re.sub(r'^[\d]+[.、。\)）]\s*', '', line)
            cleaned = re.sub(r'^[-•·]\s*', '', cleaned).strip()
            if cleaned:
                current_lines.append(cleaned)

    if current_name is not None:
        result[current_name] = current_lines[:5]

    return result


def setup_login() -> None:
    """
    Verify that claude.ai cookies are accessible from Chrome.
    No browser login needed — this just confirms the setup is correct.
    """
    print("驗證 Chrome 中的 claude.ai 登入狀態...")
    try:
        cookies = _get_claude_cookies()
        print(f"✓ 找到 {len(cookies)} 個 claude.ai cookies")
        print("✓ 設定完成！執行 python3 runner.py run 即可開始使用 Claude 摘要")
    except Exception as e:
        print(f"❌ {e}")
