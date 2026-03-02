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
