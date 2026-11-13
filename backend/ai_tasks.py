"""
Provider-agnostic AI tasks: prompt assembly + response parsing on top of a
bare ``chat(prompt, timeout_secs) -> str`` callable.

A new provider only has to supply ``chat`` and wrap it in ``AITasks``.
(claude_browser / chatgpt_browser still carry their own copies of these
functions; they are intentionally left untouched.)

Failure contract:
  * Content that gets stored or published (summaries, earnings analysis)
    raises ``AIGenerationError`` — a failure must never look like a result.
  * Auxiliary outputs (hashtags, card points, analysis, M1 score) keep the
    existing graceful-degradation behaviour that callers already rely on.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from backend import prompts
from backend.browser_common import clean_json_raw, parse_hook_sections


class AIGenerationError(RuntimeError):
    """An AI call failed (timeout, quota, login, empty or malformed output)."""


DISCLAIMER = (
    "\n\n---\n"
    "**⚠️ 負責任 AI 聲明與投資風險提示：**\n"
    "1. 本摘要由 AI 自動生成，旨在萃取作者之邏輯框架與分析觀點，不代表本平台立場。\n"
    "2. 投資涉及風險，摘要內容可能遺漏原文關鍵細節或產生解讀偏差，**請務必點擊上方連結閱讀原文** 以獲得完整資訊。\n"
    "3. 摘要中提及之情境規劃與機率分佈均為作者個人觀點，不應視為具體投資建議或獲利保證。\n"
)

_REQUIRED_SUMMARY_SECTIONS = {
    "gooaye_notes": ("本集主題總覽", "聽眾 QA", "投資心法", "提及標的"),
}


def validate_summary(summary: str, summary_style: str | None) -> None:
    """Reject non-empty but structurally incomplete channel summaries."""
    required = _REQUIRED_SUMMARY_SECTIONS.get(summary_style)
    if not required:
        return
    missing = [
        h for h in required
        if not re.search(rf"^#{{2,4}}\s+{re.escape(h)}\s*$", summary, re.MULTILINE)
    ]
    if missing:
        raise AIGenerationError(
            f"回應缺少必要章節（{summary_style}）：{', '.join(missing)}"
        )


CARD_POINTS_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "points"],
            },
        },
    },
    "required": ["hook", "sections"],
}

_JSON_OVERRIDE = (
    "\n\n【輸出格式覆寫】請忽略上面的 [HOOK]／[章節名稱] 文字格式，改以 JSON 輸出："
    "hook 為引子句子；sections 為陣列，每個元素的 name 必須與輸入章節名稱完全一致、"
    "points 為該章節的重點字串陣列（不加編號或符號前綴）。每個輸入章節都要有對應元素。"
)

_BULLET_PREFIX = re.compile(r"^(?:\d+[.、。\)）]\s*|[-•·]\s*)")


def parse_card_points_json(data: dict, section_names: list[str],
                           max_points: int) -> tuple[dict[str, list[str]], str]:
    """Validate structured card output; raise AIGenerationError if unusable."""
    if not isinstance(data, dict):
        raise AIGenerationError("字卡 JSON 不是物件")
    hook = data.get("hook")
    if not isinstance(hook, str) or not hook.strip():
        raise AIGenerationError("字卡 JSON 缺少 hook")
    by_name: dict[str, list[str]] = {}
    for item in data.get("sections") or []:
        pts = item.get("points") if isinstance(item, dict) else None
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not isinstance(pts, list) \
                or not all(isinstance(x, str) for x in pts):
            raise AIGenerationError("字卡 JSON 的 sections 格式錯誤")
        by_name[name.strip()] = [c for c in (_BULLET_PREFIX.sub("", x.strip()).strip() for x in pts) if c]
    missing = [n for n in section_names if n not in by_name]
    if missing:
        raise AIGenerationError(f"字卡 JSON 缺少章節：{', '.join(missing)}")
    result = {n: by_name[n][:max_points] for n in section_names}
    if not any(result.values()):
        raise AIGenerationError("字卡 JSON 沒有任何重點")
    return result, hook.strip()


def build_summary_request(transcript: str, title: str, summary_style: str | None,
                          host_name: str | None) -> tuple[str, int]:
    """Return (prompt, timeout_secs) for the channel's summary style."""
    is_fomo = "深入分析" in title or "深入分析" in transcript[:300]
    if summary_style == "gooaye_notes":
        # gooaye episodes are ~2x the transcript length of topic_notes channels
        return prompts.build_gooaye_summary_prompt(transcript, title), 600
    if summary_style == "topic_notes":
        return prompts.build_topic_notes_prompt(transcript, title, host_name), 300
    if is_fomo:
        return prompts.build_fomo_analysis_prompt(transcript, title), 180
    return prompts.build_summary_prompt(transcript, title), 180


def _sections_text(sections: dict[str, str]) -> str:
    return "\n\n".join(f"## {title}\n{content}" for title, content in sections.items())


def parse_hashtags(raw: str, channel_name: str) -> str:
    channel_tag = "#" + re.sub(r"\s+", "", channel_name)
    tags = [t if t.startswith("#") else f"#{t}" for t in raw.split() if t][:5]
    tags.append(channel_tag)
    return " ".join(tags)


class AITasks:
    def __init__(self, chat: Callable[..., str], label: str,
                 json_chat: Callable[..., dict] | None = None):
        """json_chat(prompt, schema, timeout_secs) -> dict enables structured card output."""
        self._chat = chat
        self._json_chat = json_chat
        self.label = label

    def _require_text(self, prompt: str, timeout_secs: int) -> str:
        text = self._chat(prompt, timeout_secs=timeout_secs)
        if not text or not text.strip():
            raise AIGenerationError(f"{self.label} 回應為空")
        return text.strip()

    # ── stored / published content: raise on failure ──────────

    def generate_summary(self, transcript: str, title: str,
                         summary_style: str | None = None,
                         host_name: str | None = None) -> str:
        prompt, timeout = build_summary_request(transcript, title, summary_style, host_name)
        summary = self._require_text(prompt, timeout)
        validate_summary(summary, summary_style)
        return summary + DISCLAIMER

    def generate_newsletter_summary(self, body: str, title: str) -> str:
        return self._require_text(prompts.build_newsletter_summary_prompt(body, title), 180)

    def generate_earnings_analysis(self, ticker: str, company_name: str, data: dict,
                                   currency: str = "USD") -> str:
        prompt = prompts.build_earnings_analysis_prompt(ticker, company_name, data, currency)
        return self._require_text(prompt, 120)

    # ── auxiliary outputs: degrade gracefully ─────────────────

    def generate_hashtags(self, summary_body: str, channel_name: str) -> str:
        try:
            raw = self._chat(prompts.build_hashtag_prompt(summary_body), timeout_secs=30)
            return parse_hashtags(raw, channel_name)
        except Exception:
            channel_tag = "#" + re.sub(r"\s+", "", channel_name)
            return f"#投資 #財經 #重點摘要 #市場分析 #股市 {channel_tag}"

    def _card_points(self, builder, sections: dict[str, str], max_points: int,
                     what: str) -> tuple[dict[str, list[str]], str]:
        if self._json_chat is not None:
            return self._card_points_json(builder, sections, max_points, what)
        try:
            raw = self._chat(builder(_sections_text(sections)), timeout_secs=120)
        except Exception as e:
            print(f"  [{self.label}] {what}生成失敗：{e}")
            return {name: [] for name in sections}, ""
        return parse_hook_sections(raw, max_points=max_points)

    def _card_points_json(self, builder, sections, max_points, what):
        """Structured output; validate, retry once, then degrade to empty."""
        names = list(sections)
        prompt = builder(_sections_text(sections)) + _JSON_OVERRIDE
        for attempt in range(2):
            try:
                data = self._json_chat(prompt, CARD_POINTS_SCHEMA, timeout_secs=120)
                return parse_card_points_json(data, names, max_points)
            except AIGenerationError as e:
                suffix = "，重試..." if attempt == 0 else ""
                print(f"  [{self.label}] {what}生成失敗{suffix}：{e}")
        return {name: [] for name in names}, ""

    def generate_card_points(self, sections):
        return self._card_points(prompts.build_card_points_prompt, sections, 5, "批次金句")

    def generate_newsletter_card_points(self, sections):
        return self._card_points(prompts.build_newsletter_card_points_prompt, sections, 4, "電子報批次金句")

    def generate_card_points_shorts(self, sections):
        return self._card_points(prompts.build_card_points_shorts_prompt, sections, 5, "Shorts 金句")

    def generate_newsletter_card_points_shorts(self, sections):
        return self._card_points(prompts.build_newsletter_card_points_shorts_prompt, sections, 4,
                                 "電子報 Shorts 金句")

    def _json_reply(self, prompt: str, timeout_secs: int) -> dict:
        raw = self._require_text(prompt, timeout_secs)
        cleaned = clean_json_raw(raw)
        if not cleaned:
            raise AIGenerationError("清理後內容為空")
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise AIGenerationError(f"JSON 解析失敗：{e}；原始前 200 字：{raw[:200]!r}") from e
        if not isinstance(data, dict):
            raise AIGenerationError(f"JSON 不是物件：{raw[:200]!r}")
        return data

    def extract_analysis(self, summary_body: str) -> dict:
        """{"mentions": [...], "industries": [...]}; empty lists after 2 failed attempts."""
        prompt = prompts.build_analysis_prompt(summary_body)
        for attempt in range(2):
            try:
                data = self._json_reply(prompt, 60)
                return {"mentions": data.get("mentions", []),
                        "industries": data.get("industries", [])}
            except Exception as e:
                suffix = "，重試..." if attempt == 0 else ""
                print(f"  [{self.label}] 分析萃取失敗{suffix}：{e}")
        return {"mentions": [], "industries": []}

    def score_m1(self, summary_body: str) -> float:
        """total/3 in 0.0–1.0; -1.0 on failure (distinct from a genuine 0)."""
        try:
            data = self._json_reply(prompts.build_m1_prompt(summary_body), 30)
            total = int(data["total"])
            if not 0 <= total <= 3:
                raise AIGenerationError(f"total 超出 0–3：{total}")
            return round(total / 3, 4)
        except Exception as e:
            print(f"  [m1] 評分失敗：{e}")
            return -1.0
