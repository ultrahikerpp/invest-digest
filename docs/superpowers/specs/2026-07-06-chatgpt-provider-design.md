# ChatGPT as a Second AI Provider — Design

## Purpose

The project currently automates claude.ai (via `backend/claude_browser.py`) to run all
summarization/analysis prompts. This adds ChatGPT (chatgpt.com) as a second, manually
selectable provider that runs the exact same prompts, so the user can switch per
invocation (e.g. when Claude is rate-limited, or to compare output quality).

Non-goals: no automatic fallback between providers, no side-by-side dual generation,
no persistence of which provider produced a given summary (frontmatter is unchanged).

## Scope

Full parity across all 13 public functions currently in `claude_browser.py`:

`generate_summary`, `generate_hashtags`, `generate_card_points`,
`generate_newsletter_card_points`, `generate_card_points_shorts`,
`generate_newsletter_card_points_shorts`, `extract_analysis`, `score_m1`,
`generate_earnings_analysis`, `generate_newsletter_summary`, `chat`, `setup_login`,
plus internal cookie/DOM helpers.

## Architecture

### 1. `backend/prompts.py` (new)

All prompt-builder functions move out of `claude_browser.py` into this shared,
provider-agnostic module (un-prefixed, public): `build_summary_prompt`,
`build_fomo_analysis_prompt`, `build_hashtag_prompt`, `build_analysis_prompt`,
`build_m1_prompt`, `build_newsletter_summary_prompt`, and the inline card-points
prompt strings (extracted into named builder functions). Both browser modules
import from here — this is what guarantees "same prompt, different site."

### 2. `backend/claude_browser.py` (existing, refactored)

Behavior unchanged. Prompt-building calls now import from `backend/prompts.py`
instead of using local `_build_*` functions.

### 3. `backend/chatgpt_browser.py` (new)

Mirrors `claude_browser.py`'s public API exactly — same 13 function names and
signatures — implemented against chatgpt.com:

- `_get_chatgpt_cookies()` — extract chatgpt.com (and openai.com/auth-related)
  cookies from Chrome via `browser_cookie3`, same pattern as
  `_get_claude_cookies()`.
- `_extract_last_response(page)` — DOM-to-markdown for ChatGPT's assistant
  message container (best-guess selectors: `[data-message-author-role="assistant"]`
  with inner `.markdown.prose`; **to be verified against the live page**, not
  taken on faith).
- `chat()` — navigate to chatgpt.com, inject cookies, submit into the prompt
  textarea (best-guess: `#prompt-textarea`), detect completion via the
  stop-generating button appearing/disappearing (best-guess:
  `[data-testid="stop-button"]`) plus the same stability-polling fallback used
  in `claude_browser.py`.
- All prompt text sourced from `backend/prompts.py` — never duplicated.

### 4. `backend/ai_provider.py` (new)

Thin dispatcher; the only module other files should import AI functions from
going forward:

```python
_PROVIDERS = {"claude": "backend.claude_browser", "chatgpt": "backend.chatgpt_browser"}

def _mod(provider: str):
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {provider!r}. Choose from: {list(_PROVIDERS)}")
    import importlib
    return importlib.import_module(_PROVIDERS[provider])

def generate_summary(transcript, title, provider="claude"):
    return _mod(provider).generate_summary(transcript, title)

# ... same forwarding pattern for all 13 functions
```

## CLI Plumbing

`runner.py` parses `sys.argv` manually (no argparse). Add:

```python
def _extract_provider(args: list[str]) -> str:
    """Pull --provider <name> out of args; default 'claude'; validate."""
    if "--provider" in args:
        i = args.index("--provider")
        if i + 1 < len(args):
            provider = args[i + 1]
            if provider not in ("claude", "chatgpt"):
                print(f"ERROR: unknown --provider {provider!r} (choices: claude, chatgpt)", file=sys.stderr)
                sys.exit(1)
            return provider
    return "claude"
```

Thread `provider: str = "claude"` through every function on the call path from
CLI to AI call, forwarding to `ai_provider`:

- **runner.py**: `cmd_run`, `cmd_cards`, `cmd_shorts_cards`, `cmd_retry`,
  `cmd_reprocess`, `cmd_approve`, `cmd_notify_latest`, `cmd_backfill_analysis`,
  `cmd_score`, `cmd_weekly`, `cmd_earnings`, `cmd_refresh_earnings`, and the
  `setup-browser` dispatch branch in `main()`.
- **worker.py**: `generate_summary(transcript, title, provider="claude")`,
  `generate_hashtags(summary_body, channel_name, provider="claude")`.
- **card_generator.py**: `generate_cards(md_path, channel_name, output_dir,
  hashtags="", provider="claude")`.
- **card_generator_shorts.py**: `generate_cards_shorts(md_path, channel_name,
  output_dir, hashtags, provider="claude")`.

All call sites currently doing `from backend.claude_browser import X` switch to
`from backend.ai_provider import X` and pass `provider=provider` through.

**Not touched** (no AI calls): `build`, `deploy`, `video`, `shorts-video`,
`trending`, `track`, `divergence`, `renormalize`, `fix-dates`,
`send-confirmations`.

## Risks & Verification

**Primary risk**: chatgpt.com's cookie-based login + DOM automation may not be
as cooperative as claude.ai's (more aggressive bot detection, different cookie/
session model). The selectors listed above are best-guess, not verified.

**De-risking step (first implementation task, before wiring the other 12
functions)**: a standalone smoke test — inject Chrome cookies, open chatgpt.com,
submit one prompt via `chat()`, confirm a real response comes back. If cookie
auth doesn't hold up, fall back to documenting a one-time interactive login
step (mirroring the existing `setup-browser` UX) instead of pure cookie
extraction.

**Testing approach**:
- `ai_provider.py` dispatch logic (unknown provider raises, correct module
  selected) gets real unit tests — this is pure Python, no browser involved.
- The browser-automation layer itself follows the existing project convention:
  `claude_browser.py` has no automated tests today, so `chatgpt_browser.py`
  won't either. Verified manually via `runner.py setup-browser --provider
  chatgpt`, then a cheap real command end-to-end
  (`runner.py earnings AAPL --provider chatgpt`).

## User Confirmation

- Usage pattern: manual per-invocation switch via `--provider`, not automatic
  fallback or dual-run comparison.
- Scope: full parity across all 13 functions.
- CLI design: `--provider` flag added to existing commands (default `claude`),
  not separate command names, not env-var config.
- User already has a ChatGPT account logged into Chrome, so cookie extraction
  has a session to read.
