"""
DQS (Data Quality Score) — rule-based scoring for investment summaries.

Currently implements M4: keyword coverage across four investment categories.
"""
from __future__ import annotations

import re
from datetime import date

# ── Keyword lists ─────────────────────────────────────────

_MACRO_KEYWORDS = [
    "聯準會", "Fed", "升息", "降息", "利率", "GDP", "CPI", "PMI",
    "通膨", "通縮", "央行", "景氣", "衰退", "就業", "非農", "殖利率", "總經", "總體經濟",
]

_SECTOR_KEYWORDS = [
    "產業", "板塊", "輪動", "供應鏈", "半導體", "科技", "金融", "房地產",
    "能源", "生技", "電動車", "AI", "雲端",
]

_EARNINGS_KEYWORDS = [
    "財報", "季報", "年報", "EPS", "每股盈餘", "營收", "毛利", "淨利", "本益比",
    "earnings", "revenue", "Q1", "Q2", "Q3", "Q4",
]

# Earnings season: mid-Jan, mid-Apr, mid-Jul, mid-Oct ± 21 days
_EARNINGS_ANCHORS = [(1, 15), (4, 15), (7, 15), (10, 15)]
_EARNINGS_WINDOW_DAYS = 21


# ── Helpers ───────────────────────────────────────────────

def _is_earnings_season(ref_date: date | None = None) -> bool:
    """Return True if ref_date falls within any quarterly earnings season window."""
    d = ref_date or date.today()
    for month, day in _EARNINGS_ANCHORS:
        anchor = date(d.year, month, day)
        if abs((d - anchor).days) <= _EARNINGS_WINDOW_DAYS:
            return True
        # Check previous year anchor for early-January dates near Dec window
        anchor_prev = date(d.year - 1, month, day)
        if abs((d - anchor_prev).days) <= _EARNINGS_WINDOW_DAYS:
            return True
    return False


def _keyword_hit(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def _has_stock_mentions(summary_text: str) -> bool:
    """
    Return True if the '## 提及標的' section contains actual stock mentions
    (i.e., is not empty and does not say '本集未提及具體標的').
    """
    match = re.search(r'##\s*提及標的\s*\n(.*?)(?=\n##|\Z)', summary_text, re.DOTALL)
    if not match:
        return False
    section_content = match.group(1).strip()
    if not section_content:
        return False
    if "本集未提及具體標的" in section_content:
        return False
    return True


# ── Public API ────────────────────────────────────────────

def score_m4(
    summary_text: str,
    reference_date: date | None = None,
) -> tuple[float, dict]:
    """
    Rule-based M4 coverage scoring.

    Categories (each worth 1 base point, 4 total):
      - 總經：macro keywords
      - 產業：sector/industry keywords
      - 財報：earnings keywords (x2 weight during earnings season)
      - 個股：explicit stock mentions in '## 提及標的' section

    During earnings season, a 財報 hit counts as 2 points toward the 4-point
    denominator, so it can single-handedly push the score to 0.5 and hitting all
    four categories yields min(5/4, 1.0) = 1.0.

    Args:
        summary_text: full summary markdown (including frontmatter is fine).
        reference_date: date used for earnings season detection; defaults to today.

    Returns:
        (m4_score, coverage_dict)
        m4_score: float in 0.0–1.0
        coverage_dict: {"總經": bool, "產業": bool, "財報": bool, "個股": bool}
    """
    coverage = {
        "總經": _keyword_hit(summary_text, _MACRO_KEYWORDS),
        "產業": _keyword_hit(summary_text, _SECTOR_KEYWORDS),
        "財報": _keyword_hit(summary_text, _EARNINGS_KEYWORDS),
        "個股": _has_stock_mentions(summary_text),
    }

    in_earnings = _is_earnings_season(reference_date)

    # Each category = 1 point; 財報 doubles during earnings season
    # Denominator stays at 4 to keep the scale anchored
    earned = 0.0
    for category, hit in coverage.items():
        if not hit:
            continue
        if category == "財報" and in_earnings:
            earned += 2.0
        else:
            earned += 1.0

    m4_score = round(min(1.0, earned / 4.0), 4)
    return m4_score, coverage
