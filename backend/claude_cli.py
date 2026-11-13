"""
Claude via the local Claude Code CLI (`claude -p`) — no browser, no cookies.

Uses the CLI's own login (claude.ai subscription or API credentials), so
usage counts against Claude Code's quota. Every failure raises
AIGenerationError; nothing is ever returned as if it were a result.
"""
from __future__ import annotations

import json
import subprocess
import tempfile

from backend.ai_tasks import AIGenerationError, AITasks

_ERR_SNIPPET = 300


_BASE_FLAGS = [
    "--tools", "",
    "--disable-slash-commands",
    "--no-session-persistence",
    "--setting-sources", "local",
    "--strict-mcp-config",  # no --mcp-config given => load no MCP servers at all
]


def _run(extra_flags: list[str], prompt: str, timeout_secs: int) -> subprocess.CompletedProcess:
    """Run `claude -p` (prompt via stdin) in an empty temp dir; never returns on infra failure.

    `--setting-sources local` (empty in that dir) keeps ~/.claude's CLAUDE.md,
    hooks and skills out of the prompt — "user" would load them and they leak
    into the output. Built-in tools, MCP servers (untrusted transcript text must
    not be able to reach e.g. desktop-automation tools), slash commands and
    session persistence are all off.
    """
    cmd = ["claude", "-p", *extra_flags, *_BASE_FLAGS]
    with tempfile.TemporaryDirectory(prefix="claude-cli-") as cwd:
        try:
            return subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                timeout=timeout_secs, cwd=cwd,
            )
        except subprocess.TimeoutExpired as e:
            raise AIGenerationError(f"claude CLI 逾時（{timeout_secs} 秒）") from e
        except FileNotFoundError as e:
            raise AIGenerationError("找不到 claude CLI，請確認已安裝並在 PATH 中") from e


def _fail(proc: subprocess.CompletedProcess) -> AIGenerationError:
    parts = [(proc.stderr or "").strip(), (proc.stdout or "").strip()]
    detail = " | ".join(x for x in parts if x)[:_ERR_SNIPPET]
    return AIGenerationError(f"claude CLI 失敗（exit {proc.returncode}）：{detail}")


def chat(prompt: str, timeout_secs: int = 180) -> str:
    """Send `prompt` to `claude -p` and return the reply text."""
    proc = _run(["--output-format", "text"], prompt, timeout_secs)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise _fail(proc)
    if not out:
        raise AIGenerationError("claude CLI 回應為空")
    return out


def chat_json(prompt: str, schema: dict, timeout_secs: int = 180) -> dict:
    """Send `prompt` with a JSON Schema; return the validated `structured_output` dict."""
    proc = _run(["--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False)],
                prompt, timeout_secs)
    if proc.returncode != 0:
        raise _fail(proc)
    try:
        result = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError) as e:
        raise AIGenerationError(f"claude CLI 回應不是 JSON：{(proc.stdout or '')[:_ERR_SNIPPET]!r}") from e
    if not isinstance(result, dict) or result.get("is_error"):
        raise AIGenerationError(f"claude CLI 回報錯誤：{str(result.get('result') if isinstance(result, dict) else result)[:_ERR_SNIPPET]}")
    structured = result.get("structured_output")
    if not isinstance(structured, dict):
        raise AIGenerationError("claude CLI 未回傳 structured_output")
    return structured


_tasks = AITasks(
    lambda prompt, timeout_secs=180: chat(prompt, timeout_secs),
    label="claude-cli",
    json_chat=lambda prompt, schema, timeout_secs=180: chat_json(prompt, schema, timeout_secs),
)

generate_summary = _tasks.generate_summary
generate_newsletter_summary = _tasks.generate_newsletter_summary
generate_hashtags = _tasks.generate_hashtags
generate_card_points = _tasks.generate_card_points
generate_newsletter_card_points = _tasks.generate_newsletter_card_points
generate_card_points_shorts = _tasks.generate_card_points_shorts
generate_newsletter_card_points_shorts = _tasks.generate_newsletter_card_points_shorts
extract_analysis = _tasks.extract_analysis
score_m1 = _tasks.score_m1
generate_earnings_analysis = _tasks.generate_earnings_analysis


def setup_login() -> None:
    """Check that the claude CLI is installed and logged in."""
    print("驗證 claude CLI 登入狀態...")
    try:
        proc = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"❌ 無法執行 claude CLI：{e}")
        return
    print(proc.stdout.strip() or proc.stderr.strip())
    if proc.returncode == 0:
        print("✓ 設定完成！執行 python3 runner.py run --provider claude-cli 即可使用")
    else:
        print("❌ 尚未登入，請先在終端機執行 `claude` 完成登入")
