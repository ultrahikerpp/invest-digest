import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from backend.ai_tasks import AITasks, AIGenerationError, validate_summary


def _tasks(response=None, exc=None):
    calls = []

    def chat(prompt, timeout_secs=180):
        calls.append((prompt, timeout_secs))
        if exc:
            raise exc
        return response

    return AITasks(chat, label="test"), calls


GOOAYE_OK = "\n".join(f"## {h}\n內容" for h in ("本集主題總覽", "聽眾 QA", "投資心法", "提及標的"))


def test_summary_appends_disclaimer_and_uses_style_timeout():
    t, calls = _tasks(GOOAYE_OK)
    out = t.generate_summary("逐字稿", "EP1", summary_style="gooaye_notes")
    assert out.startswith(GOOAYE_OK)
    assert "負責任 AI 聲明" in out
    assert calls[0][1] == 600


def test_summary_topic_notes_timeout_300_and_default_180():
    t, calls = _tasks("# ok")
    t.generate_summary("x", "t", summary_style="topic_notes", host_name="Jenny")
    t.generate_summary("x", "t")
    assert [c[1] for c in calls] == [300, 180]


def test_summary_missing_required_sections_raises():
    t, _ = _tasks("## 本集主題總覽\n只有一節")
    with pytest.raises(AIGenerationError, match="缺少必要章節"):
        t.generate_summary("x", "t", summary_style="gooaye_notes")


def test_summary_empty_response_raises():
    t, _ = _tasks("   ")
    with pytest.raises(AIGenerationError):
        t.generate_summary("x", "t")


def test_summary_chat_error_propagates():
    t, _ = _tasks(exc=AIGenerationError("limit"))
    with pytest.raises(AIGenerationError, match="limit"):
        t.generate_summary("x", "t")


def test_validate_summary_ignores_styles_without_requirements():
    validate_summary("anything", None)
    validate_summary("anything", "topic_notes")


def test_hashtags_parse_and_fallback():
    t, _ = _tasks("股票 #AI 半導體 #台積電 美股 多餘")
    assert t.generate_hashtags("body", "Gooaye 股癌") == "#股票 #AI #半導體 #台積電 #美股 #Gooaye股癌"
    t, _ = _tasks(exc=AIGenerationError("x"))
    assert t.generate_hashtags("body", "A B").endswith("#AB")


def test_card_points_degrade_to_empty_on_failure():
    t, _ = _tasks(exc=AIGenerationError("x"))
    points, hook = t.generate_card_points({"摘要": "內容", "結論": "內容"})
    assert points == {"摘要": [], "結論": []} and hook == ""


def test_card_points_parse_hook_and_sections():
    t, _ = _tasks("[HOOK]\n一句話\n\n[摘要]\n1. 點一\n2. 點二")
    points, hook = t.generate_card_points({"摘要": "內容"})
    assert hook == "一句話" and points == {"摘要": ["點一", "點二"]}


def test_extract_analysis_retries_once_then_parses():
    responses = iter(["not json", '```json\n{"mentions": [{"name": "NVDA"}], "industries": ["AI"]}\n```'])
    t = AITasks(lambda p, timeout_secs=180: next(responses), label="test")
    assert t.extract_analysis("body") == {"mentions": [{"name": "NVDA"}], "industries": ["AI"]}


def test_extract_analysis_gives_empty_after_two_failures():
    t, calls = _tasks("garbage")
    assert t.extract_analysis("body") == {"mentions": [], "industries": []}
    assert len(calls) == 2


def test_score_m1_normalises_and_returns_minus_one_on_failure():
    t, _ = _tasks('{"total": 2}')
    assert t.score_m1("body") == round(2 / 3, 4)
    t, _ = _tasks(exc=AIGenerationError("x"))
    assert t.score_m1("body") == -1.0


def test_earnings_failure_raises_instead_of_returning_warning_text():
    t, _ = _tasks(exc=AIGenerationError("limit"))
    with pytest.raises(AIGenerationError):
        t.generate_earnings_analysis("NVDA", "Nvidia", {"charts": {}}, "USD")


# ── structured (JSON) card points ─────────────────────────

GOOD = {"hook": "驚人引子？", "sections": [
    {"name": "摘要", "points": ["1. 點一", "• 點二", "- 點三", "點四", "點五", "點六"]},
    {"name": "結論", "points": ["結論一"]},
]}


def _json_tasks(*replies):
    """AITasks whose json_chat yields replies in order (an Exception instance is raised)."""
    calls = []
    it = iter(replies)

    def json_chat(prompt, schema, timeout_secs=180):
        calls.append((prompt, schema, timeout_secs))
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    def text_chat(prompt, timeout_secs=180):
        raise AssertionError("text chat must not be used for card points")

    return AITasks(text_chat, label="test", json_chat=json_chat), calls


def test_json_card_points_maps_sections_cleans_bullets_and_caps():
    t, calls = _json_tasks(GOOD)
    points, hook = t.generate_card_points({"摘要": "a", "結論": "b"})
    assert hook == "驚人引子？"
    assert points == {"摘要": ["點一", "點二", "點三", "點四", "點五"], "結論": ["結論一"]}  # capped at 5
    prompt, schema, timeout = calls[0]
    assert "JSON" in prompt and "## 摘要" in prompt  # original prompt kept + JSON override
    assert schema["required"] == ["hook", "sections"] and timeout == 120


def test_json_newsletter_card_points_cap_is_four():
    t, _ = _json_tasks(GOOD)
    points, _ = t.generate_newsletter_card_points({"摘要": "a", "結論": "b"})
    assert len(points["摘要"]) == 4


@pytest.mark.parametrize("bad", [
    {"hook": "", "sections": [{"name": "摘要", "points": ["a"]}, {"name": "結論", "points": ["b"]}]},
    {"hook": "h", "sections": [{"name": "摘要", "points": ["a"]}]},                      # missing 結論
    {"hook": "h", "sections": [{"name": "摘要", "points": []}, {"name": "結論", "points": []}]},  # nothing at all
    {"hook": "h", "sections": [{"name": "摘要", "points": "oops"}, {"name": "結論", "points": ["b"]}]},
    AIGenerationError("quota"),
])
def test_json_card_points_retry_once_then_succeed(bad):
    t, calls = _json_tasks(bad, GOOD)
    points, hook = t.generate_card_points({"摘要": "a", "結論": "b"})
    assert len(calls) == 2 and hook == "驚人引子？" and points["結論"] == ["結論一"]


def test_json_card_points_degrade_after_two_failures(capsys):
    t, calls = _json_tasks(AIGenerationError("x"), {"hook": "", "sections": []})
    points, hook = t.generate_card_points({"摘要": "a", "結論": "b"})
    assert len(calls) == 2  # exactly one retry
    assert points == {"摘要": [], "結論": []} and hook == ""
    assert "失敗" in capsys.readouterr().out


def test_json_path_covers_all_four_card_variants():
    for method in ("generate_card_points", "generate_newsletter_card_points",
                   "generate_card_points_shorts", "generate_newsletter_card_points_shorts"):
        t, calls = _json_tasks(GOOD)
        points, hook = getattr(t, method)({"摘要": "a", "結論": "b"})
        assert hook and len(calls) == 1, method


def test_score_m1_rejects_out_of_range_or_missing_total():
    for reply in ('{"total": 5}', '{"total": -1}', '{"other": 1}', '{"total": "2/3"}', '[1, 2]'):
        t, _ = _tasks(reply)
        assert t.score_m1("body") == -1.0, reply


def test_extract_analysis_non_object_json_gives_empty():
    t, calls = _tasks('["not", "an", "object"]')
    assert t.extract_analysis("body") == {"mentions": [], "industries": []}
    assert len(calls) == 2
