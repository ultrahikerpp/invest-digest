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
python3 runner.py reprocess --channel <channel_id>   # single channel only (also scopes the auto-approve)
python3 runner.py reprocess --channel <channel_id> --limit <n>  # cap episodes regenerated this run; re-run to continue

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

# Use ChatGPT instead of Claude for any AI-calling command (default is claude)
python3 runner.py run --provider chatgpt
python3 runner.py setup-browser --provider chatgpt   # one-time chatgpt.com login check

# Smart refresh all earnings in earnings_watchlist.json (skip if fresh, update numbers if same quarter, full refresh if new quarter)
python3 runner.py refresh-earnings
python3 runner.py refresh-earnings --deploy  # refresh + build + deploy
python3 runner.py refresh-earnings --force   # force full refresh for all tickers

# Synthesize cross-channel weekly digest from past 7 days, then auto-email subscribers (once per ISO week, idempotent)
python3 runner.py weekly
python3 runner.py weekly-digest   # send the subscriber email directly, without regenerating the digest article

# Preview static site locally
cd docs && python3 -m http.server 8000

# Crontab (daily 8:30am run, Saturday 9am earnings refresh, Sunday 5:30pm weekly-digest email)
# 30 8 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py run >> data/runner.log 2>&1
# 0 9 * * 6 cd /path/to/investment-digest && ./venv/bin/python runner.py refresh-earnings --deploy >> data/runner.log 2>&1
# 30 17 * * 0 cd /path/to/investment-digest && ./venv/bin/python runner.py weekly-digest >> data/runner.log 2>&1
```

**Workflow:** `run` fetches + summarises → sends review email → user reviews → `approve` generates hashtags/cards/video + auto-deploys to GitHub Pages.

**API Key setup:** Copy `.env.example` to `.env` and set `GMAIL_APP_PASSWORD`. The `.env` file is gitignored and never committed.

## Architecture

Local-only Python scripts + GitHub Pages static site. No web server required.

### Local Scripts (project root)

- **`runner.py`** — Main CLI. Commands: `run`, `approve`, `build`, `cards`, `video`, `deploy`, `notify`, `setup-browser`. Reads channels from `channels.json`, uses SQLite DB for status tracking, imports functions from `backend/`.

- **`build_site.py`** — Static site generator. Reads `data/summaries/**/*.md` → writes `docs/data/episodes.json` + copies `docs/summaries/*.md`.

- **`channels.json`** — Channel configuration. Add new channels here. Optional `summary_style` field selects a channel-specific summary prompt (`"gooaye_notes"` = topic-based notes with 聽眾 QA / 投資心法 sections for Gooaye 股癌; `"topic_notes"` = topic-based notes with 關鍵數據 / 投資觀念 sections for daily news-style channels, pair with `host_name` for the 「◯◯認為」 voice; omit for the generic six-section format).

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
