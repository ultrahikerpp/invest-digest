"""
Provider dispatcher for AI browser-automation calls.

All callers (runner.py, worker.py, card_generator*.py) should import from
here instead of importing backend.claude_browser or backend.chatgpt_browser
directly, so the caller only has to thread a `provider` string through.
"""
from __future__ import annotations

import importlib

_PROVIDERS = {
    "claude": "backend.claude_browser",
    "chatgpt": "backend.chatgpt_browser",
}


def _mod(provider: str):
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {provider!r}. Choose from: {list(_PROVIDERS)}")
    return importlib.import_module(_PROVIDERS[provider])


def generate_summary(transcript: str, title: str, provider: str = "claude",
                     summary_style: str | None = None) -> str:
    return _mod(provider).generate_summary(transcript, title, summary_style=summary_style)


def generate_newsletter_summary(body: str, title: str, provider: str = "claude") -> str:
    return _mod(provider).generate_newsletter_summary(body, title)


def generate_hashtags(summary_body: str, channel_name: str, provider: str = "claude") -> str:
    return _mod(provider).generate_hashtags(summary_body, channel_name)


def generate_card_points(sections: dict[str, str], provider: str = "claude") -> tuple[dict[str, list[str]], str]:
    return _mod(provider).generate_card_points(sections)


def generate_newsletter_card_points(sections: dict[str, str], provider: str = "claude") -> tuple[dict[str, list[str]], str]:
    return _mod(provider).generate_newsletter_card_points(sections)


def generate_card_points_shorts(sections: dict[str, str], provider: str = "claude") -> tuple[dict[str, list[str]], str]:
    return _mod(provider).generate_card_points_shorts(sections)


def generate_newsletter_card_points_shorts(sections: dict[str, str], provider: str = "claude") -> tuple[dict[str, list[str]], str]:
    return _mod(provider).generate_newsletter_card_points_shorts(sections)


def extract_analysis(summary_body: str, provider: str = "claude") -> dict:
    return _mod(provider).extract_analysis(summary_body)


def score_m1(summary_body: str, provider: str = "claude") -> float:
    return _mod(provider).score_m1(summary_body)


def generate_earnings_analysis(
    ticker: str, company_name: str, data: dict, currency: str = "USD", provider: str = "claude"
) -> str:
    return _mod(provider).generate_earnings_analysis(ticker, company_name, data, currency)


def chat(prompt: str, timeout_secs: int = 180, provider: str = "claude") -> str:
    return _mod(provider).chat(prompt, timeout_secs=timeout_secs)


def setup_login(provider: str = "claude") -> None:
    return _mod(provider).setup_login()
