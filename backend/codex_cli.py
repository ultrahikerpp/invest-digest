"""
Codex via the local Codex CLI (`codex exec`) — no browser, no cookies.

Uses the CLI's own ChatGPT/API login, so usage counts against that plan.
Every failure raises AIGenerationError; nothing is ever returned as if it
were a result.

Isolation: Codex loads far more ambient context than Claude's CLI, so each
call runs in a throwaway HOME + CODEX_HOME that only holds a copy of auth.json
(a token refreshed during the call is synced back, otherwise a rotated refresh
token would silently log the user out of the real ~/.codex).
That keeps ~/.codex/AGENTS.md, config.toml (MCP servers, plugins),
~/.agents/skills and memories out of the prompt — transcript text is
untrusted and must not reach those tools — and cut the per-call context
from ~11-31K to ~2K tokens. The shell, apps, plugins, hooks, memories and
web search features are switched off as well.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.ai_tasks import AIGenerationError, AITasks

_ERR_SNIPPET = 300

_FLAGS = [
    "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check",
    "-s", "read-only", "--color", "never",
    "--disable", "shell_tool", "--disable", "unified_exec", "--disable", "apps",
    "--disable", "plugins", "--disable", "hooks", "--disable", "memories",
    "-c", "web_search=disabled",
]


def _real_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _find_codex() -> str:
    # Terminal wrappers (e.g. cmux) shadow `codex` with a shim that injects MCP
    # servers; resolve the real binary by dropping their directories from PATH.
    entries = [p for p in os.environ.get("PATH", "").split(os.pathsep)
               if p and "cmux-cli-shims" not in p]
    found = shutil.which("codex", path=os.pathsep.join(entries))
    if not found:
        raise AIGenerationError("找不到 codex CLI，請確認已安裝（brew install codex）並在 PATH 中")
    return found


def strictify_schema(schema: dict) -> dict:
    """Codex's --output-schema (OpenAI strict mode) rejects objects that don't set
    additionalProperties:false and list every property in `required`."""
    out = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)
    return out


def _sync_auth_back(temp_auth: Path, real_auth: Path, original: bytes) -> None:
    """Persist a token that codex refreshed inside the throwaway CODEX_HOME."""
    try:
        new = temp_auth.read_bytes()
        if new == original or not new.strip():
            return
        if not isinstance(json.loads(new), dict):
            return
        target = real_auth.resolve()
        tmp = target.with_name(target.name + ".tmp-sync")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(new)
        os.replace(tmp, target)
    except (OSError, ValueError):
        pass  # never let bookkeeping mask the call's own result


def _fail(proc: subprocess.CompletedProcess) -> AIGenerationError:
    parts = [(proc.stderr or "").strip(), (proc.stdout or "").strip()]
    detail = " | ".join(x for x in parts if x)[-_ERR_SNIPPET:]
    return AIGenerationError(f"codex CLI 失敗（exit {proc.returncode}）：{detail}")


def _exec(prompt: str, timeout_secs: int, schema: dict | None = None) -> str:
    """Run `codex exec` (prompt via stdin) in an isolated temp tree; return the final message."""
    auth = _real_codex_home() / "auth.json"
    if not auth.exists():
        raise AIGenerationError("codex CLI 尚未登入，請先執行 `codex login`")
    try:
        auth_bytes = auth.read_bytes()
    except OSError as e:
        raise AIGenerationError(f"無法讀取 codex 登入資料：{e}") from e
    binary = _find_codex()

    with tempfile.TemporaryDirectory(prefix="codex-cli-") as tmp:
        root = Path(tmp)
        home, codex_home, work = root / "home", root / "codex_home", root / "work"
        for d in (home, codex_home, work):
            d.mkdir()
        temp_auth = codex_home / "auth.json"
        fd = os.open(temp_auth, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(auth_bytes)
        out_file = root / "last_message.txt"

        cmd = [binary, "exec", *_FLAGS, "-C", str(work), "-o", str(out_file)]
        if schema is not None:
            schema_file = root / "schema.json"
            schema_file.write_text(json.dumps(strictify_schema(schema), ensure_ascii=False))
            cmd += ["--output-schema", str(schema_file)]
        cmd.append("-")

        env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(codex_home)}
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                  timeout=timeout_secs, cwd=work, env=env)
        except subprocess.TimeoutExpired as e:
            raise AIGenerationError(f"codex CLI 逾時（{timeout_secs} 秒）") from e
        except FileNotFoundError as e:
            raise AIGenerationError("找不到 codex CLI，請確認已安裝並在 PATH 中") from e
        except OSError as e:
            raise AIGenerationError(f"無法執行 codex CLI：{e}") from e
        finally:
            _sync_auth_back(temp_auth, auth, auth_bytes)

        if proc.returncode != 0:
            raise _fail(proc)
        try:
            text = out_file.read_text(encoding="utf-8").strip() if out_file.exists() else ""
        except (OSError, UnicodeDecodeError) as e:
            raise AIGenerationError(f"無法讀取 codex 回應：{e}") from e

    if not text:
        raise AIGenerationError("codex CLI 回應為空")
    return text


def chat(prompt: str, timeout_secs: int = 180) -> str:
    """Send `prompt` to `codex exec` and return the reply text."""
    return _exec(prompt, timeout_secs)


def chat_json(prompt: str, schema: dict, timeout_secs: int = 180) -> dict:
    """Send `prompt` with a JSON Schema; return the parsed final message as a dict."""
    text = _exec(prompt, timeout_secs, schema=schema)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise AIGenerationError(f"codex CLI 回應不是 JSON：{text[:_ERR_SNIPPET]!r}") from e
    if not isinstance(data, dict):
        raise AIGenerationError(f"codex CLI 回應不是 JSON 物件：{text[:_ERR_SNIPPET]!r}")
    return data


_tasks = AITasks(
    lambda prompt, timeout_secs=180: chat(prompt, timeout_secs),
    label="codex-cli",
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
    """Check that the codex CLI is installed and logged in."""
    print("驗證 codex CLI 登入狀態...")
    try:
        proc = subprocess.run([_find_codex(), "login", "status"], capture_output=True,
                              text=True, timeout=30)
    except (AIGenerationError, subprocess.TimeoutExpired) as e:
        print(f"❌ 無法執行 codex CLI：{e}")
        return
    print((proc.stdout or proc.stderr).strip())
    if proc.returncode == 0:
        print("✓ 設定完成！執行 python3 runner.py run --provider codex-cli 即可使用")
    else:
        print("❌ 尚未登入，請先在終端機執行 `codex login`")
