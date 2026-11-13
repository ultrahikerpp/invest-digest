"""runner.py must survive AIGenerationError from CLI providers (no traceback, no bad data saved)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import runner
from backend.ai_tasks import AIGenerationError


def test_cmd_earnings_exits_cleanly_and_saves_nothing_on_ai_failure(monkeypatch, tmp_path, capsys):
    from backend import earnings_fetcher, ai_provider
    data = {"company_name": "Nvidia", "currency": "USD",
            "charts": {"revenue": {"labels": ["Q1"]}}}
    monkeypatch.setattr(earnings_fetcher, "fetch_earnings_data", lambda t: dict(data), raising=False)
    monkeypatch.setattr(ai_provider, "generate_earnings_analysis",
                        lambda *a, **k: (_ for _ in ()).throw(AIGenerationError("limit")))
    monkeypatch.setattr(runner, "BASE_DIR", tmp_path)

    with pytest.raises(SystemExit) as ei:
        runner.cmd_earnings("NVDA", provider="claude-cli")

    assert ei.value.code == 1
    assert "財報分析生成失敗" in capsys.readouterr().err
    assert not (tmp_path / "docs" / "data" / "earnings" / "NVDA.json").exists()
