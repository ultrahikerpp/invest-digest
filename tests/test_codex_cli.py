import json
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from backend import codex_cli
from backend.ai_tasks import AIGenerationError

SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "string"}, "items": {"type": "array", "items": {
        "type": "object", "properties": {"n": {"type": "string"}, "opt": {"type": "string"}},
        "required": ["n"]}}},
    "required": ["x"],
}


@pytest.fixture
def fake_codex_home(tmp_path, monkeypatch):
    home = tmp_path / "real_codex_home"
    home.mkdir()
    (home / "auth.json").write_text('{"token": "secret"}')
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(codex_cli.shutil, "which", lambda name, path=None: "/opt/homebrew/bin/codex")
    return home


def _arg(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def install_run(monkeypatch, reply="hello", returncode=0, stderr="", capture=None, on_run=None):
    """Patch subprocess.run to emulate `codex exec`: writes `reply` to the -o file."""
    def fake_run(cmd, **kwargs):
        out = _arg(cmd, "-o")
        if on_run is not None:
            on_run(Path(kwargs["env"]["CODEX_HOME"]) / "auth.json")
        if reply is not None:
            Path(out).write_text(reply)
        if capture is not None:
            capture["cmd"], capture["kwargs"] = cmd, kwargs
            env = kwargs["env"]
            auth = Path(env["CODEX_HOME"]) / "auth.json"
            capture["auth_is_symlink"] = auth.is_symlink()
            capture["auth_content"] = auth.read_text()
            capture["auth_mode"] = auth.stat().st_mode & 0o777
            if "--output-schema" in cmd:
                capture["schema"] = json.loads(Path(_arg(cmd, "--output-schema")).read_text())
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    monkeypatch.setattr(codex_cli.subprocess, "run", fake_run)


def test_chat_sends_prompt_via_stdin_with_isolation_flags(monkeypatch, fake_codex_home):
    seen = {}
    install_run(monkeypatch, reply="  hello \n", capture=seen)

    assert codex_cli.chat("長逐字稿", timeout_secs=42) == "hello"

    cmd, kw = seen["cmd"], seen["kwargs"]
    assert cmd[0] == "/opt/homebrew/bin/codex" and cmd[1] == "exec"
    assert cmd[-1] == "-" and "長逐字稿" not in cmd            # prompt only via stdin
    assert kw["input"] == "長逐字稿" and kw["timeout"] == 42
    for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check"):
        assert flag in cmd
    assert _arg(cmd, "-s") == "read-only"
    disabled = {cmd[i + 1] for i, a in enumerate(cmd) if a == "--disable"}
    assert {"shell_tool", "unified_exec", "apps", "plugins", "hooks", "memories"} <= disabled
    assert "web_search=disabled" in cmd


def test_chat_runs_in_temp_home_with_only_auth_copied(monkeypatch, fake_codex_home):
    seen = {}
    install_run(monkeypatch, capture=seen)
    codex_cli.chat("x")

    env = seen["kwargs"]["env"]
    # Neither the real HOME nor the real CODEX_HOME may be exposed: they carry
    # global AGENTS.md, MCP servers, plugins and ~/.agents skills.
    assert env["HOME"] != os.environ["HOME"]
    assert Path(env["CODEX_HOME"]) != fake_codex_home
    assert not seen["auth_is_symlink"]                      # a copy, so a rename can't dangle
    assert seen["auth_content"] == '{"token": "secret"}' and seen["auth_mode"] == 0o600
    assert Path(seen["kwargs"]["cwd"]) != Path.cwd()


def test_binary_lookup_skips_cmux_shim_dirs(monkeypatch, fake_codex_home):
    paths = {}
    monkeypatch.setattr(codex_cli.shutil, "which",
                        lambda name, path=None: (paths.update(path=path), "/opt/homebrew/bin/codex")[1])
    monkeypatch.setenv("PATH", "/a/cmux-cli-shims/UUID:/usr/bin:/opt/homebrew/bin")
    install_run(monkeypatch)
    codex_cli.chat("x")
    assert "cmux-cli-shims" not in paths["path"] and "/usr/bin" in paths["path"]


def test_chat_raises_when_binary_missing(monkeypatch, fake_codex_home):
    monkeypatch.setattr(codex_cli.shutil, "which", lambda name, path=None: None)
    with pytest.raises(AIGenerationError, match="找不到"):
        codex_cli.chat("x")


def test_chat_raises_when_not_logged_in(monkeypatch, fake_codex_home):
    (fake_codex_home / "auth.json").unlink()
    with pytest.raises(AIGenerationError, match="登入"):
        codex_cli.chat("x")


def test_chat_raises_on_timeout(monkeypatch, fake_codex_home):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(codex_cli.subprocess, "run", fake_run)
    with pytest.raises(AIGenerationError, match="逾時"):
        codex_cli.chat("x", timeout_secs=1)


def test_chat_raises_on_nonzero_exit_with_stderr(monkeypatch, fake_codex_home):
    install_run(monkeypatch, reply="partial", returncode=1, stderr="usage limit reached")
    with pytest.raises(AIGenerationError, match="usage limit reached"):
        codex_cli.chat("x")


@pytest.mark.parametrize("reply", [None, "", "  \n"])
def test_chat_raises_on_missing_or_empty_output(monkeypatch, fake_codex_home, reply):
    install_run(monkeypatch, reply=reply)
    with pytest.raises(AIGenerationError, match="空"):
        codex_cli.chat("x")


def test_generate_summary_failure_is_not_returned_as_summary(monkeypatch, fake_codex_home):
    install_run(monkeypatch, reply=None, returncode=1, stderr="boom")
    with pytest.raises(AIGenerationError):
        codex_cli.generate_summary("transcript", "title")


# ── structured output ─────────────────────────────────────

def test_strictify_schema_adds_additional_properties_false_and_requires_all():
    original = json.loads(json.dumps(SCHEMA))
    strict = codex_cli.strictify_schema(SCHEMA)
    assert SCHEMA == original                               # input not mutated
    assert strict["additionalProperties"] is False
    assert strict["required"] == ["x", "items"]
    item = strict["properties"]["items"]["items"]
    assert item["additionalProperties"] is False and item["required"] == ["n", "opt"]


def test_chat_json_passes_strict_schema_file_and_returns_dict(monkeypatch, fake_codex_home):
    seen = {}
    install_run(monkeypatch, reply='{"x": "ok", "items": []}', capture=seen)

    assert codex_cli.chat_json("提示", SCHEMA, timeout_secs=9) == {"x": "ok", "items": []}
    assert seen["schema"] == codex_cli.strictify_schema(SCHEMA)
    assert seen["kwargs"]["input"] == "提示" and seen["kwargs"]["timeout"] == 9


@pytest.mark.parametrize("reply", ["not json", "[1, 2]", "", None, '"str"'])
def test_chat_json_raises_on_bad_output(monkeypatch, fake_codex_home, reply):
    install_run(monkeypatch, reply=reply)
    with pytest.raises(AIGenerationError):
        codex_cli.chat_json("x", SCHEMA)


def test_chat_json_raises_on_nonzero_exit(monkeypatch, fake_codex_home):
    install_run(monkeypatch, reply='{"x": "a"}', returncode=1, stderr="schema rejected")
    with pytest.raises(AIGenerationError, match="schema rejected"):
        codex_cli.chat_json("x", SCHEMA)


def test_card_points_use_structured_path_with_one_retry(monkeypatch):
    replies = iter([
        {"hook": "", "sections": []},  # invalid -> retry
        {"hook": "引子", "sections": [{"name": "摘要", "points": ["1. 重點一", "重點二"]}]},
    ])
    monkeypatch.setattr(codex_cli, "chat_json", lambda prompt, schema, timeout_secs=180: next(replies))
    points, hook = codex_cli.generate_card_points({"摘要": "內容"})
    assert hook == "引子" and points == {"摘要": ["重點一", "重點二"]}


# ── auth.json handling (token refresh must not log the user out) ──

def _rewrite_like_codex_refresh(auth: Path):
    """Codex refreshes via temp file + rename, which replaces any symlink."""
    tmp = auth.with_name("auth.json.tmp")
    tmp.write_text('{"token": "refreshed"}')
    os.replace(tmp, auth)


def test_refreshed_token_is_synced_back_to_real_auth(monkeypatch, fake_codex_home):
    install_run(monkeypatch, on_run=_rewrite_like_codex_refresh)
    codex_cli.chat("x")
    assert (fake_codex_home / "auth.json").read_text() == '{"token": "refreshed"}'


def test_refreshed_token_is_synced_back_even_when_the_call_fails(monkeypatch, fake_codex_home):
    install_run(monkeypatch, returncode=1, stderr="boom", on_run=_rewrite_like_codex_refresh)
    with pytest.raises(AIGenerationError):
        codex_cli.chat("x")
    assert (fake_codex_home / "auth.json").read_text() == '{"token": "refreshed"}'


@pytest.mark.parametrize("bad", ["", "not json", "[1]"])
def test_invalid_auth_is_never_synced_back(monkeypatch, fake_codex_home, bad):
    install_run(monkeypatch, on_run=lambda auth: auth.write_text(bad))
    codex_cli.chat("x")
    assert (fake_codex_home / "auth.json").read_text() == '{"token": "secret"}'


def test_unchanged_auth_is_left_alone(monkeypatch, fake_codex_home):
    real = fake_codex_home / "auth.json"
    before = real.stat().st_mtime_ns
    install_run(monkeypatch)
    codex_cli.chat("x")
    assert real.stat().st_mtime_ns == before


def test_relative_codex_home_works(monkeypatch, tmp_path, fake_codex_home):
    monkeypatch.chdir(fake_codex_home.parent)
    monkeypatch.setenv("CODEX_HOME", fake_codex_home.name)  # relative path
    seen = {}
    install_run(monkeypatch, capture=seen)
    codex_cli.chat("x")
    assert seen["auth_content"] == '{"token": "secret"}'


# ── every failure must surface as AIGenerationError ───────

def test_chat_raises_on_oserror_from_subprocess(monkeypatch, fake_codex_home):
    def fake_run(cmd, **kwargs):
        raise PermissionError("not executable")

    monkeypatch.setattr(codex_cli.subprocess, "run", fake_run)
    with pytest.raises(AIGenerationError, match="not executable"):
        codex_cli.chat("x")


def test_chat_raises_on_undecodable_output(monkeypatch, fake_codex_home):
    def fake_run(cmd, **kwargs):
        Path(_arg(cmd, "-o")).write_bytes(b"\xff\xfe\xfa")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(codex_cli.subprocess, "run", fake_run)
    with pytest.raises(AIGenerationError):
        codex_cli.chat("x")
