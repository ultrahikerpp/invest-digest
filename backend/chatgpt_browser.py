#!/usr/bin/env python3
"""
Generate summaries/hashtags by automating ChatGPT's web UI via Playwright.

Mirrors backend/claude_browser.py's approach: extract chatgpt.com session
cookies directly from the user's Chrome browser (no login step needed),
inject them into a Playwright context, and interact with the chat interface
headlessly.

Prerequisites:
  1. Be logged in to chatgpt.com in Chrome at least once.
  2. On first run, macOS may prompt "python3 wants to access your keychain" —
     click Allow. This is needed to decrypt Chrome's cookie database.
"""
from __future__ import annotations

import time

CHATGPT_NEW_CHAT_URL = "https://chatgpt.com/"


# ── Cookie extraction ─────────────────────────────────────

def _get_chatgpt_cookies() -> list[dict]:
    """
    Extract chatgpt.com and openai.com cookies from the user's Chrome browser.

    macOS: Chrome encrypts cookies with a key stored in the system Keychain.
           On first run, macOS will ask 'python3 wants to access your keychain' — click Allow.
    """
    try:
        import browser_cookie3

        def _convert(c) -> dict:
            return {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path or "/",
                "secure": bool(c.secure),
                "httpOnly": False,
                "sameSite": "Lax",
            }

        chatgpt_cookies = [_convert(c) for c in browser_cookie3.chrome(domain_name="chatgpt.com")]
        openai_cookies = [_convert(c) for c in browser_cookie3.chrome(domain_name="openai.com")]

        if not chatgpt_cookies:
            raise RuntimeError(
                "未找到 chatgpt.com cookies，請確認已在 Chrome 中登入 chatgpt.com"
            )

        return chatgpt_cookies + openai_cookies

    except ImportError:
        raise RuntimeError(
            "請安裝 browser-cookie3：pip install browser-cookie3"
        )
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"無法從 Chrome 取得登入狀態：{e}\n"
            "請確認：\n"
            "  1. Chrome 已安裝且曾登入過 chatgpt.com\n"
            "  2. 若 macOS 詢問 Keychain 存取權限，請點選「允許」"
        )


# ── Browser helpers ───────────────────────────────────────
#
# NOTE: the selectors below (#prompt-textarea, [data-message-author-role],
# [data-testid="stop-button"]) are best-guess pending live verification in
# this task's Step 2. If the smoke test fails, open chatgpt.com in Chrome
# DevTools, inspect the prompt input and the assistant message container,
# and update these selectors accordingly.

def _extract_last_response(page) -> str:
    """Extract the last assistant message text from the ChatGPT page as markdown."""
    return page.evaluate("""() => {
        function nodeToMd(node) {
            if (node.nodeType === 3) return node.textContent;
            const tag = (node.tagName || '').toLowerCase();
            const children = () => Array.from(node.childNodes).map(nodeToMd).join('');
            if (tag === 'h1') return '# ' + children() + '\\n\\n';
            if (tag === 'h2') return '## ' + children() + '\\n\\n';
            if (tag === 'h3') return '### ' + children() + '\\n\\n';
            if (tag === 'h4') return '#### ' + children() + '\\n\\n';
            if (tag === 'li') return '- ' + children().trim() + '\\n';
            if (tag === 'ul' || tag === 'ol') return children() + '\\n';
            if (tag === 'p') return children() + '\\n\\n';
            if (tag === 'strong' || tag === 'b') return '**' + children() + '**';
            if (tag === 'em' || tag === 'i') return '*' + children() + '*';
            if (tag === 'br') return '\\n';
            if (tag === 'code') return '`' + children() + '`';
            if (tag === 'pre') return '```\\n' + children() + '\\n```\\n\\n';
            if (tag === 'a') return children();
            if (tag === 'hr') return '\\n---\\n\\n';
            if (tag === 'table') return children() + '\\n';
            if (tag === 'thead') {
                const content = children();
                const firstTr = node.querySelector('tr');
                const cols = firstTr ? firstTr.querySelectorAll('td, th').length : 1;
                const sep = '| ' + Array(cols).fill('---').join(' | ') + ' |\\n';
                return content + sep;
            }
            if (tag === 'tbody') return children();
            if (tag === 'tr') {
                const cells = Array.from(node.querySelectorAll('td, th'));
                return '| ' + cells.map(c => c.innerText.trim()).join(' | ') + ' |\\n';
            }
            return children();
        }

        const els = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (els.length) return nodeToMd(els[els.length - 1]).trim();
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
    return prev


def chat(prompt: str, timeout_secs: int = 180) -> str:
    """
    Inject Chrome cookies into a Playwright browser, open chatgpt.com,
    send `prompt`, and return ChatGPT's response text.

    No login step needed — cookies are read from the user's Chrome browser.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    cookies = _get_chatgpt_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                "--no-first-run",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        ctx.add_cookies(cookies)

        try:
            page = ctx.new_page()
            page.goto(CHATGPT_NEW_CHAT_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(1)

            time.sleep(2)
            url = page.url
            page_title = page.title().lower()

            def _is_cloudflare() -> bool:
                if any(k in url for k in ("challenge_redirect", "__cf_chl_rt_tk", "challenges.cloudflare.com")):
                    return True
                if any(k in page_title for k in ("just a moment", "security verification", "verify you are human")):
                    return True
                if page.query_selector('[class*="cf-turnstile"], [id*="cf-chl"], [name="cf-turnstile-response"]') is not None:
                    return True
                return False

            if "auth0.openai.com" in url or "auth.openai.com" in url:
                raise RuntimeError(
                    "ChatGPT 登入狀態已過期或需要重新驗證。請在 Chrome 中重新登入 chatgpt.com，"
                    "然後重新執行 runner.py"
                )
            elif _is_cloudflare():
                print(
                    "\n  [chatgpt] ⚠️  偵測到 Cloudflare 驗證，"
                    "請在瀏覽器視窗中手動勾選核取方塊後等待...",
                    flush=True,
                )
                try:
                    page.wait_for_selector('#prompt-textarea', timeout=120000)
                    print("  [chatgpt] Cloudflare 驗證完成，繼續執行")
                except PWTimeout:
                    raise RuntimeError(
                        "等待 Cloudflare 驗證逾時（120 秒）。"
                        "請在 Chrome 中重新登入 chatgpt.com 後再試。"
                    )
            else:
                print("  [chatgpt] 等待介面載入...", end="", flush=True)
                try:
                    page.wait_for_selector('#prompt-textarea', timeout=30000)
                    print(" 完成")
                except PWTimeout:
                    raise RuntimeError(
                        "ChatGPT 登入狀態已過期。請在 Chrome 中重新登入 chatgpt.com，"
                        "然後重新執行 runner.py"
                    )

            input_el = page.locator('#prompt-textarea').first
            input_el.click()

            page.evaluate(
                "(text) => document.execCommand('insertText', false, text)",
                prompt,
            )
            time.sleep(0.4)

            page.keyboard.press("Enter")
            print("  [chatgpt] 傳送完成，等待回應...", end="", flush=True)

            stop_appeared = False
            try:
                page.wait_for_selector(
                    '[data-testid="stop-button"]',
                    timeout=12000,
                )
                stop_appeared = True
                page.wait_for_selector(
                    '[data-testid="stop-button"]',
                    state="hidden",
                    timeout=timeout_secs * 1000,
                )
            except PWTimeout:
                if not stop_appeared:
                    pass

            time.sleep(1)
            response = _wait_for_stable_response(page, timeout_secs=30)
            print(" 完成")

            if not response:
                raise RuntimeError("無法擷取回應內容，請確認 chatgpt.com 已正常回應")

            return response

        finally:
            ctx.close()
            browser.close()
