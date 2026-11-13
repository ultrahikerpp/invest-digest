import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from backend import claude_cli
from backend.ai_tasks import AIGenerationError


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_chat_sends_prompt_via_stdin_in_neutral_cwd(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return _completed(stdout="  hello  \n")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)

    assert claude_cli.chat("長逐字稿", timeout_secs=42) == "hello"
    assert seen["kwargs"]["input"] == "長逐字稿"
    assert seen["kwargs"]["timeout"] == 42
    assert Path(seen["kwargs"]["cwd"]) != Path.cwd()
    assert "長逐字稿" not in seen["cmd"]  # never on argv
    assert "-p" in seen["cmd"]
    # "user" would load ~/.claude/CLAUDE.md + hooks into the summary prompt
    i = seen["cmd"].index("--setting-sources")
    assert seen["cmd"][i + 1] == "local"


def test_chat_raises_on_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    with pytest.raises(AIGenerationError, match="逾時"):
        claude_cli.chat("x", timeout_secs=1)


def test_chat_raises_on_nonzero_exit_with_output_in_message(monkeypatch):
    monkeypatch.setattr(
        claude_cli.subprocess, "run",
        lambda cmd, **kw: _completed(stdout="Usage limit reached", stderr="", returncode=1),
    )
    with pytest.raises(AIGenerationError, match="Usage limit reached"):
        claude_cli.chat("x")


def test_chat_raises_on_empty_output(monkeypatch):
    monkeypatch.setattr(claude_cli.subprocess, "run", lambda cmd, **kw: _completed(stdout="  \n"))
    with pytest.raises(AIGenerationError, match="空"):
        claude_cli.chat("x")


def test_chat_raises_when_cli_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    with pytest.raises(AIGenerationError, match="找不到"):
        claude_cli.chat("x")


def test_generate_summary_failure_is_not_returned_as_summary(monkeypatch):
    # Regression: browser providers turned failures into a normal-looking
    # markdown body that got saved as a successful summary.
    monkeypatch.setattr(
        claude_cli.subprocess, "run", lambda cmd, **kw: _completed(stdout="", returncode=1, stderr="boom"),
    )
    with pytest.raises(AIGenerationError):
        claude_cli.generate_summary("transcript", "title")


# ── chat_json (structured output) ─────────────────────────

import json

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


def _json_result(**fields):
    base = {"type": "result", "subtype": "success", "is_error": False, "result": "", "num_turns": 2}
    base.update(fields)
    return json.dumps(base)


def test_chat_json_passes_schema_and_returns_structured_output(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return _completed(stdout=_json_result(structured_output={"x": "ok"}))

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)

    assert claude_cli.chat_json("提示", SCHEMA, timeout_secs=9) == {"x": "ok"}
    cmd = seen["cmd"]
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--setting-sources") + 1] == "local"
    assert seen["kwargs"]["input"] == "提示" and seen["kwargs"]["timeout"] == 9


@pytest.mark.parametrize("stdout, returncode", [
    (_json_result(), 0),                                   # no structured_output
    (_json_result(is_error=True, result="limit", structured_output={"x": "a"}), 0),
    ("not json at all", 0),
    ("", 0),
    (_json_result(structured_output={"x": "a"}), 1),       # non-zero exit
])
def test_chat_json_raises_on_bad_results(monkeypatch, stdout, returncode):
    monkeypatch.setattr(claude_cli.subprocess, "run",
                        lambda cmd, **kw: _completed(stdout=stdout, returncode=returncode))
    with pytest.raises(AIGenerationError):
        claude_cli.chat_json("x", SCHEMA)


def test_chat_json_raises_on_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    with pytest.raises(AIGenerationError, match="逾時"):
        claude_cli.chat_json("x", SCHEMA, timeout_secs=1)


def test_card_points_use_structured_path_with_one_retry(monkeypatch):
    replies = iter([
        {"hook": "", "sections": []},  # invalid -> retry
        {"hook": "引子", "sections": [{"name": "摘要", "points": ["1. 重點一", "重點二"]}]},
    ])
    monkeypatch.setattr(claude_cli, "chat_json", lambda prompt, schema, timeout_secs=180: next(replies))
    points, hook = claude_cli.generate_card_points({"摘要": "內容"})
    assert hook == "引子" and points == {"摘要": ["重點一", "重點二"]}


def test_chat_disables_mcp_servers(monkeypatch):
    # Regression: MCP servers from ~/.claude settings (e.g. desktop automation)
    # were still reachable by the model while it processed untrusted transcripts.
    seen = {}
    monkeypatch.setattr(claude_cli.subprocess, "run",
                        lambda cmd, **kw: (seen.update(cmd=cmd), _completed(stdout="ok"))[1])
    claude_cli.chat("x")
    assert "--strict-mcp-config" in seen["cmd"] and "--mcp-config" not in seen["cmd"]


def test_chat_error_message_includes_stderr_and_stdout(monkeypatch):
    monkeypatch.setattr(claude_cli.subprocess, "run",
                        lambda cmd, **kw: _completed(stdout="partial", stderr="rate limited", returncode=1))
    with pytest.raises(AIGenerationError) as ei:
        claude_cli.chat("x")
    assert "rate limited" in str(ei.value) and "partial" in str(ei.value)


def test_chat_raises_on_oserror_from_subprocess(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise PermissionError("not executable")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    with pytest.raises(AIGenerationError, match="not executable"):
        claude_cli.chat("x")
