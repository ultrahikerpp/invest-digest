# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Fetch new episodes, transcribe, and summarize → sends review notification email
python3 runner.py run

# Fetch a single channel only
python3 runner.py run --channel <channel_id>

# Approve all pending episodes: hashtags + cards + video + auto-deploy
python3 runner.py approve

# Re-generate ALL episode summaries with current prompt, then approve + deploy
python3 runner.py reprocess

# Regenerate the static site (docs/)
python3 runner.py build

# Build + commit + push to GitHub Pages
python3 runner.py deploy

# Generate PNG cards for a video
python3 runner.py cards <video_id>

# Generate MP4 video from cards
python3 runner.py video <video_id>

# One-time Claude browser login setup (run before first use)
python3 runner.py setup-browser

# Preview static site locally
cd docs && python3 -m http.server 8000

# Crontab (daily at 8:30am run, 9:00am notify)
# 30 8 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py run >> data/runner.log 2>&1
# 0 9 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py notify >> data/runner.log 2>&1
```

**Workflow:** `run` fetches + summarises → sends review email → user reviews → `approve` generates hashtags/cards/video + auto-deploys to GitHub Pages.

**API Key setup:** Copy `.env.example` to `.env` and set `GMAIL_APP_PASSWORD`. The `.env` file is gitignored and never committed.

## Architecture

Local-only Python scripts + GitHub Pages static site. No web server required.

### Local Scripts (project root)

- **`runner.py`** — Main CLI. Commands: `run`, `approve`, `build`, `cards`, `video`, `deploy`, `notify`, `setup-browser`. Reads channels from `channels.json`, uses SQLite DB for status tracking, imports functions from `backend/`.

- **`build_site.py`** — Static site generator. Reads `data/summaries/**/*.md` → writes `docs/data/episodes.json` + copies `docs/summaries/*.md`.

- **`channels.json`** — Channel configuration. Add new channels here.

### Backend (`backend/`)

- **`worker.py`** — Core functions imported by `runner.py`:
  1. `get_latest_videos(channel_id)` — YouTube RSS feed
  2. `get_youtube_transcript(video_id)` — Downloads audio + Whisper transcription
  3. `generate_summary(transcript, title)` — delegates to `claude_browser`
  4. `send_notification_email(subject, body)` — Gmail SMTP

- **`claude_browser.py`** — Claude AI via browser automation (Playwright + Chrome cookies):
  - `generate_summary()` — investment summary from transcript
  - `generate_hashtags()` — 5 keyword hashtags
  - `generate_card_points()` — bullet points for each card section

- **`card_generator.py`** — Generates PNG summary cards (Pillow)
- **`video_maker.py`** — Assembles PNG cards into MP4

### Static Site (`docs/`)

- **`docs/index.html`** — Vanilla JS SPA for GitHub Pages. Fetches `data/episodes.json` and `summaries/*.md` statically. Hash routing (`#/channel/<id>`). No backend calls.
- **`docs/data/episodes.json`** — Generated episode index (by `build_site.py`)
- **`docs/summaries/*.md`** — Copied summary files

### Data Layer (`data/`)

- **`data/subscriptions.db`** — SQLite; stores processed video_ids for deduplication
- **`data/summaries/*.md`** — Markdown summaries with YAML frontmatter (source of truth)
- **`data/transcripts/`** — Raw Whisper output (local only, gitignored)
- **`data/cards/`** — PNG card images (local only)
- **`data/videos/`** — MP4 videos (local only)

### Frontmatter Format

```
---
title: EP639 | 🐗
video_id: Y3UKwjPIVeE
channel_id: UC23rnlQU_qE3cec9x709peA
channel_name: Gooaye 股癌
published: 2026-02-27
processed: 2026-02-27
---
```

### Key Design Decisions

- **No web server**: Static GitHub Pages site; all data pre-generated at build time.
- **No YouTube Data API key**: RSS feeds for video listing.
- **No Gemini/OpenAI API**: Uses Claude.ai web UI via Playwright browser automation; reads Chrome's local session cookies.
- **Summaries as files**: Markdown files are the source of truth; `episodes.json` is derived.
- **Two-phase workflow**: `run` → `pending_review`; `approve` → `done` + auto-deploy.
- **Status tracking via SQLite**: `data/subscriptions.db` tracks `pending_review` / `done` per episode.

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
