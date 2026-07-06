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

import re
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


# ── Public API ────────────────────────────────────────────

def generate_summary(transcript: str, title: str) -> str:
    """Generate investment summary via ChatGPT browser automation."""
    from backend import prompts

    is_fomo_analysis = "深入分析" in title or "深入分析" in transcript[:300]

    if is_fomo_analysis:
        prompt = prompts.build_fomo_analysis_prompt(transcript, title)
    else:
        prompt = prompts.build_summary_prompt(transcript, title)

    try:
        summary = chat(prompt, timeout_secs=180)

        disclaimer = (
            "\n\n---\n"
            "**⚠️ 負責任 AI 聲明與投資風險提示：**\n"
            "1. 本摘要由 AI 自動生成，旨在萃取作者之邏輯框架與分析觀點，不代表本平台立場。\n"
            "2. 投資涉及風險，摘要內容可能遺漏原文關鍵細節或產生解讀偏差，**請務必點擊上方連結閱讀原文** 以獲得完整資訊。\n"
            "3. 摘要中提及之情境規劃與機率分佈均為作者個人觀點，不應視為具體投資建議或獲利保證。\n"
        )
        return summary + disclaimer
    except Exception as e:
        return (
            f"# {title}\n\n"
            f"⚠️ ChatGPT 瀏覽器摘要失敗：{e}\n\n"
            f"## 內容前段\n\n{transcript[:1000]}"
        )


def generate_newsletter_summary(body: str, title: str) -> str:
    """Generate investment summary for a newsletter article via ChatGPT browser automation."""
    from backend import prompts

    prompt = prompts.build_newsletter_summary_prompt(body, title)
    try:
        return chat(prompt, timeout_secs=180)
    except Exception as e:
        return (
            f"# {title}\n\n"
            f"⚠️ ChatGPT 瀏覽器摘要失敗：{e}\n\n"
            f"## 電子報前段\n\n{body[:1000]}"
        )


def generate_hashtags(summary_body: str, channel_name: str) -> str:
    """Generate 5 keyword hashtags via ChatGPT browser automation."""
    from backend import prompts

    channel_tag = "#" + re.sub(r'\s+', '', channel_name)
    prompt = prompts.build_hashtag_prompt(summary_body)
    try:
        raw = chat(prompt, timeout_secs=30)
        tags = [t if t.startswith("#") else f"#{t}" for t in raw.split() if t][:5]
        tags.append(channel_tag)
        return " ".join(tags)
    except Exception:
        return f"#投資 #財經 #重點摘要 #市場分析 #股市 {channel_tag}"


def generate_card_points(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """
    Given a dict of {section_title: content}, return ({section_title: [bullet points]}, hook_text).
    All sections are processed in a single browser session (one chat call).
    """
    from backend import prompts
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = prompts.build_card_points_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [chatgpt] 批次金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=5)


def generate_newsletter_card_points(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """Newsletter-specific variant of generate_card_points."""
    from backend import prompts
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = prompts.build_newsletter_card_points_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [chatgpt] 電子報批次金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=4)


def generate_card_points_shorts(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """Generate Shorts-optimised bullet points for each section, plus a HOOK sentence."""
    from backend import prompts
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = prompts.build_card_points_shorts_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [chatgpt] Shorts 金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=5)


def generate_newsletter_card_points_shorts(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """Newsletter-specific variant of generate_card_points_shorts."""
    from backend import prompts
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = prompts.build_newsletter_card_points_shorts_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [chatgpt] 電子報 Shorts 金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=4)


def extract_analysis(summary_body: str) -> dict:
    """
    Extract structured mentions and industries from a summary via ChatGPT.
    Returns {"mentions": [...], "industries": [...]} or empty lists on failure.
    Retries once on transient errors (empty response, JSON parse failure).
    """
    import json
    from backend import prompts
    from backend.browser_common import clean_json_raw

    prompt = prompts.build_analysis_prompt(summary_body)

    for attempt in range(2):
        try:
            raw = chat(prompt, timeout_secs=60)
        except RuntimeError as e:
            if attempt == 0:
                print(f"  [chatgpt] 回應擷取失敗，重試... ({e})")
                continue
            print(f"  [chatgpt] 分析萃取失敗：{e}")
            return {"mentions": [], "industries": []}

        raw = raw.strip()
        if not raw:
            if attempt == 0:
                print(f"  [chatgpt] 回應為空，重試...")
                continue
            print(f"  [chatgpt] 分析萃取失敗：回應為空")
            return {"mentions": [], "industries": []}

        try:
            cleaned = clean_json_raw(raw)
            if not cleaned:
                raise ValueError("清理後內容為空")
            data = json.loads(cleaned)
            return {
                "mentions": data.get("mentions", []),
                "industries": data.get("industries", []),
            }
        except Exception as e:
            if attempt == 0:
                print(f"  [chatgpt] JSON 解析失敗，重試... ({e})")
                continue
            print(f"  [chatgpt] 分析萃取失敗：{e}")
            print(f"  [chatgpt] 原始回應前 200 字：{raw[:200]!r}")

    return {"mentions": [], "industries": []}


def score_m1(summary_body: str) -> float:
    """
    Score summary on M1 (signal quality) via ChatGPT browser.

    Returns total/3 normalised to 0.0-1.0.
    Returns -1.0 on failure (distinguishable from a genuine 0 score).
    """
    import json
    from backend import prompts
    from backend.browser_common import clean_json_raw

    prompt = prompts.build_m1_prompt(summary_body)
    try:
        raw = chat(prompt, timeout_secs=30)
    except Exception as e:
        print(f"  [m1] chat 失敗：{e}")
        return -1.0

    raw = raw.strip()
    if not raw:
        print(f"  [m1] 回應為空")
        return -1.0

    try:
        cleaned = clean_json_raw(raw)
        if not cleaned:
            raise ValueError("清理後內容為空")
        data = json.loads(cleaned)
        total = int(data.get("total", 0))
        return round(total / 3, 4)
    except Exception as e:
        print(f"  [m1] JSON 解析失敗：{e}  原始：{raw[:200]!r}")
        return -1.0


def generate_earnings_analysis(ticker: str, company_name: str, data: dict, currency: str = 'USD') -> str:
    """Generate quarterly earnings analysis via ChatGPT browser automation."""
    from backend import prompts

    prompt = prompts.build_earnings_analysis_prompt(ticker, company_name, data, currency)
    try:
        return chat(prompt, timeout_secs=120)
    except Exception as e:
        return f"⚠️ ChatGPT 分析失敗：{e}"


def setup_login() -> None:
    """
    Verify that chatgpt.com cookies are accessible from Chrome.
    No browser login needed — this just confirms the setup is correct.
    """
    print("驗證 Chrome 中的 chatgpt.com 登入狀態...")
    try:
        cookies = _get_chatgpt_cookies()
        print(f"✓ 找到 {len(cookies)} 個 chatgpt.com cookies")
        print("✓ 設定完成！執行 python3 runner.py run --provider chatgpt 即可開始使用 ChatGPT 摘要")
    except Exception as e:
        print(f"❌ {e}")
