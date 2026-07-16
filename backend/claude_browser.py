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


# ── Prompt builders (shared across providers) ─────────────────

from backend.prompts import (
    build_summary_prompt as _build_summary_prompt,
    build_gooaye_summary_prompt as _build_gooaye_summary_prompt,
    build_fomo_analysis_prompt as _build_fomo_analysis_prompt,
    build_analysis_prompt as _build_analysis_prompt,
    build_m1_prompt as _build_m1_prompt,
    build_hashtag_prompt as _build_hashtag_prompt,
    build_newsletter_summary_prompt as _build_newsletter_summary_prompt,
    build_card_points_prompt,
    build_newsletter_card_points_prompt,
    build_card_points_shorts_prompt,
    build_newsletter_card_points_shorts_prompt,
    build_earnings_analysis_prompt,
)


# ── Cookie extraction ─────────────────────────────────────

def _get_claude_cookies() -> list[dict]:
    """
    Extract claude.ai and Google account cookies from the user's Chrome browser.
    Google cookies are needed so that if claude.ai redirects to Google OAuth,
    the Playwright session can re-authenticate silently without prompting for login.

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

        claude_cookies = [_convert(c) for c in browser_cookie3.chrome(domain_name="claude.ai")]
        google_cookies = [_convert(c) for c in browser_cookie3.chrome(domain_name="google.com")]

        if not claude_cookies:
            raise RuntimeError(
                "未找到 claude.ai cookies，請確認已在 Chrome 中登入 claude.ai"
            )

        return claude_cookies + google_cookies

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
            "  1. Chrome 已安裝且曾登入過 claude.ai\n"
            "  2. 若 macOS 詢問 Keychain 存取權限，請點選「允許」"
        )


# ── Browser helpers ───────────────────────────────────────

def _extract_last_response(page) -> str:
    """Extract the last assistant message text from the Claude page as markdown."""
    return page.evaluate("""() => {
        // Convert a DOM node to markdown text, preserving headings, lists, etc.
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

        // Primary: claude.ai uses div[class*="font-claude-response"] for response body
        let els = document.querySelectorAll('div[class*="font-claude-response"]');
        if (els.length) {
            const last = els[els.length - 1];
            // Actual answer text lives in .standard-markdown containers;
            // thinking/tool-use block labels sit outside them and must not
            // leak into the extracted summary.
            const md = last.querySelectorAll('.standard-markdown');
            if (md.length) {
                return Array.from(md).map(nodeToMd).join('\\n\\n').trim();
            }
            return nodeToMd(last).trim();
        }

        // Fallback: paragraph-level response class
        els = document.querySelectorAll('p[class*="font-claude-response-body"]');
        if (els.length) {
            return Array.from(els).map(el => el.innerText.trim()).join('\\n\\n');
        }

        return '';
    }""") or ""


def _generation_running(page) -> bool:
    """True while claude.ai is still thinking or streaming the response."""
    return page.evaluate(
        """() => !!document.querySelector('button[aria-label="Stop response"]')
             || !!document.querySelector('[data-is-streaming="true"]')"""
    )


def _wait_for_stable_response(page, timeout_secs: int = 180) -> str:
    """Wait until generation finishes, then until the response text stops
    changing for 3 consecutive seconds.

    While generation is running the visible text is a thinking status label or
    a growing partial answer, so it must never count as stable. Returns "" on
    timeout — a partial capture saved as a summary is worse than a visible
    failure.
    """
    prev = ""
    stable_count = 0
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        if _generation_running(page):
            prev = ""
            stable_count = 0
            time.sleep(2)
            continue
        current = _extract_last_response(page)
        if current and current == prev:
            stable_count += 1
            if stable_count >= 3:
                return current
        else:
            stable_count = 0
            prev = current
        time.sleep(1)
    return ""


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
            channel="chrome",  # use installed Chrome to reduce bot detection
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
            page.goto(CLAUDE_NEW_CHAT_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(1)  # let JS redirect settle before checking URL

            # ── Verify session is valid ───────────────────
            # Give the page a moment to settle before checking state
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

            # Google OAuth redirect: cookies should handle it silently,
            # but wait up to 15s for the redirect back to claude.ai.
            if "accounts.google.com" in url or "google.com/signin" in url:
                print(
                    "\n  [claude] ⚠️  偵測到 Google 登入重導，等待自動驗證...",
                    flush=True,
                )
                try:
                    page.wait_for_url("**/claude.ai/**", timeout=15000)
                    page.wait_for_selector('[contenteditable="true"]', timeout=15000)
                    print("  [claude] Google 驗證完成，繼續執行")
                except PWTimeout:
                    raise RuntimeError(
                        "Google 登入驗證逾時。請在 Chrome 中確認已登入 Google 帳號，"
                        "然後重新執行 runner.py"
                    )
            elif _is_cloudflare():
                print(
                    "\n  [claude] ⚠️  偵測到 Cloudflare 驗證，"
                    "請在瀏覽器視窗中手動勾選核取方塊後等待...",
                    flush=True,
                )
                try:
                    page.wait_for_selector('[contenteditable="true"]', timeout=120000)
                    print("  [claude] Cloudflare 驗證完成，繼續執行")
                except PWTimeout:
                    raise RuntimeError(
                        "等待 Cloudflare 驗證逾時（120 秒）。"
                        "請在 Chrome 中重新登入 claude.ai 後再試。"
                    )
            else:
                print("  [claude] 等待介面載入...", end="", flush=True)
                try:
                    page.wait_for_selector('[contenteditable="true"]', timeout=30000)
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
            # Confirm generation started (best effort), then give the whole
            # timeout budget to one wait that only accepts text captured
            # after generation has fully finished. Extended thinking alone
            # can run for minutes before any answer text appears.
            try:
                page.wait_for_selector(
                    'button[aria-label="Stop response"]',
                    timeout=12000,
                )
            except PWTimeout:
                pass  # generation may have finished fast or button missed

            response = _wait_for_stable_response(page, timeout_secs=timeout_secs)
            print(" 完成")

            if not response:
                raise RuntimeError("無法擷取回應內容，請確認 claude.ai 已正常回應")

            return response

        finally:
            ctx.close()
            browser.close()


# ── Public API ────────────────────────────────────────────

def generate_summary(transcript: str, title: str, summary_style: str | None = None,
                     host_name: str | None = None) -> str:
    """Generate investment summary via Claude browser automation.

    summary_style: per-channel style from channels.json; "gooaye_notes" and
    "topic_notes" use topic-based prompts and take precedence over the FOMO
    title sniff. host_name: 主持人稱謂 for topic_notes（如「游庭皓」「Jenny」）.
    """
    from backend.prompts import build_topic_notes_prompt as _build_topic_notes_prompt

    is_fomo_analysis = "深入分析" in title or "深入分析" in transcript[:300]

    if summary_style == "gooaye_notes":
        prompt = _build_gooaye_summary_prompt(transcript, title)
    elif summary_style == "topic_notes":
        prompt = _build_topic_notes_prompt(transcript, title, host_name)
    elif is_fomo_analysis:
        prompt = _build_fomo_analysis_prompt(transcript, title)
    else:
        prompt = _build_summary_prompt(transcript, title)

    # Topic-based styles produce longer responses, and claude.ai's extended
    # thinking alone can run 4+ minutes on them; give generation more headroom
    # (gooaye episodes are ~2x the transcript length of topic_notes channels).
    if summary_style == "gooaye_notes":
        timeout_secs = 600
    elif summary_style == "topic_notes":
        timeout_secs = 300
    else:
        timeout_secs = 180

    try:
        summary = chat(prompt, timeout_secs=timeout_secs)

        # Post-processing: Append Disclaimer for accountability
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
            f"⚠️ Claude 瀏覽器摘要失敗：{e}\n\n"
            f"## 內容前段\n\n{transcript[:1000]}"
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


def generate_card_points(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """
    Given a dict of {section_title: content}, return ({section_title: [bullet points]}, hook_text).
    All sections are processed in a single browser session (one chat call).

    Points: 4-5 per section, 8-14 Chinese characters each (short, punchy).
    Hook: 15-20 character sentence for the opening card.
    """
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = build_card_points_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [claude] 批次金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=5)


def generate_newsletter_card_points(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """
    Newsletter-specific variant of generate_card_points.

    Newsletter content is analytically dense (6+ sub-topics, long sentences).
    Uses relaxed constraints: 15-25 Chinese chars per bullet, 3-4 bullets per section.
    The 各主題重點 section is summarised across all sub-topics into key takeaways.
    """
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = build_newsletter_card_points_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [claude] 電子報批次金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=4)


# ── JSON cleanup (shared across providers) ─────────────────

from backend.browser_common import clean_json_raw as _clean_json_raw


def extract_analysis(summary_body: str) -> dict:
    """
    Extract structured mentions and industries from a summary via Claude.
    Returns {"mentions": [...], "industries": [...]} or empty lists on failure.
    Retries once on transient errors (empty response, JSON parse failure).
    """
    import json

    prompt = _build_analysis_prompt(summary_body)

    for attempt in range(2):
        try:
            raw = chat(prompt, timeout_secs=60)
        except RuntimeError as e:
            if attempt == 0:
                print(f"  [claude] 回應擷取失敗，重試... ({e})")
                continue
            print(f"  [claude] 分析萃取失敗：{e}")
            return {"mentions": [], "industries": []}

        raw = raw.strip()
        if not raw:
            if attempt == 0:
                print(f"  [claude] 回應為空，重試...")
                continue
            print(f"  [claude] 分析萃取失敗：回應為空")
            return {"mentions": [], "industries": []}

        try:
            cleaned = _clean_json_raw(raw)
            if not cleaned:
                raise ValueError("清理後內容為空")
            data = json.loads(cleaned)
            return {
                "mentions": data.get("mentions", []),
                "industries": data.get("industries", []),
            }
        except Exception as e:
            if attempt == 0:
                print(f"  [claude] JSON 解析失敗，重試... ({e})")
                continue
            print(f"  [claude] 分析萃取失敗：{e}")
            print(f"  [claude] 原始回應前 200 字：{raw[:200]!r}")

    return {"mentions": [], "industries": []}


# ── Newsletter summary ─────────────────────────────────────

def generate_newsletter_summary(body: str, title: str) -> str:
    """Generate investment summary for a newsletter article via Claude browser automation."""
    prompt = _build_newsletter_summary_prompt(body, title)
    try:
        return chat(prompt, timeout_secs=180)
    except Exception as e:
        return (
            f"# {title}\n\n"
            f"⚠️ Claude 瀏覽器摘要失敗：{e}\n\n"
            f"## 電子報前段\n\n{body[:1000]}"
        )


def score_m1(summary_body: str) -> float:
    """
    Score summary on M1 (signal quality) via Claude browser.

    Returns total/3 normalised to 0.0–1.0.
    Returns -1.0 on failure (distinguishable from a genuine 0 score).
    """
    import json

    prompt = _build_m1_prompt(summary_body)
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
        cleaned = _clean_json_raw(raw)
        if not cleaned:
            raise ValueError("清理後內容為空")
        data = json.loads(cleaned)
        total = int(data.get("total", 0))
        return round(total / 3, 4)
    except Exception as e:
        print(f"  [m1] JSON 解析失敗：{e}  原始：{raw[:200]!r}")
        return -1.0


def generate_card_points_shorts(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """
    Generate Shorts-optimised bullet points for each section, plus a HOOK sentence.

    Points: 2-3 per section, 8-12 Chinese characters each.
    Hook: 15-20 character sentence for the opening card.

    Returns (points_dict, hook_text).
    """
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = build_card_points_shorts_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [claude] Shorts 金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=5)


def generate_newsletter_card_points_shorts(sections: dict[str, str]) -> tuple[dict[str, list[str]], str]:
    """
    Newsletter-specific variant of generate_card_points_shorts.

    Relaxed constraints for dense analytical content: 15-25 chars per bullet, 3-4 per section.
    """
    from backend.browser_common import parse_hook_sections

    section_names = list(sections.keys())
    sections_text = "\n\n".join(
        f"## {title}\n{content}" for title, content in sections.items()
    )
    prompt = build_newsletter_card_points_shorts_prompt(sections_text)

    try:
        raw = chat(prompt, timeout_secs=120)
    except Exception as e:
        print(f"  [claude] 電子報 Shorts 金句生成失敗：{e}")
        return {name: [] for name in section_names}, ""

    return parse_hook_sections(raw, max_points=4)


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


def generate_earnings_analysis(ticker: str, company_name: str, data: dict, currency: str = 'USD') -> str:
    """Generate quarterly earnings analysis via Claude browser automation."""
    prompt = build_earnings_analysis_prompt(ticker, company_name, data, currency)
    try:
        return chat(prompt, timeout_secs=120)
    except Exception as e:
        return f"⚠️ Claude 分析失敗：{e}"
