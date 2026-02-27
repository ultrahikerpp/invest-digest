# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Fetch new episodes, transcribe, and summarize
python3 runner.py run

# Fetch a single channel only
python3 runner.py run --channel <channel_id>

# Regenerate the static site (site/)
python3 runner.py build

# Build + commit + push to GitHub Pages
python3 runner.py deploy

# Generate PNG cards for a video
python3 runner.py cards <video_id>

# Generate MP4 video from cards
python3 runner.py video <video_id>

# Preview static site locally
cd site && python3 -m http.server 8000

# Crontab (daily at 8am)
# 0 8 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py run >> data/runner.log 2>&1
```

**Required environment variable:** `GEMINI_API_KEY` for AI summary generation.

## Architecture

Local-only Python scripts + GitHub Pages static site. No web server required.

### Local Scripts (project root)

- **`runner.py`** — Main CLI. Commands: `run`, `build`, `cards`, `video`, `deploy`. Reads channels from `channels.json`, uses SQLite DB for deduplication, imports functions from `backend/worker.py`.

- **`build_site.py`** — Static site generator. Reads `data/summaries/*.md` → writes `site/data/episodes.json` + copies `site/summaries/*.md`.

- **`channels.json`** — Channel configuration. Add new channels here.

### Backend (`backend/`)

- **`worker.py`** — Core functions imported by `runner.py`:
  1. `get_latest_videos(channel_id)` — YouTube RSS feed
  2. `get_youtube_transcript(video_id)` — Downloads audio + Whisper transcription
  3. `generate_summary(transcript, title)` — Gemini 2.5 Flash API

- **`card_generator.py`** — Generates PNG summary cards (Pillow)
- **`video_maker.py`** — Assembles PNG cards into MP4

### Static Site (`site/`)

- **`site/index.html`** — Vanilla JS SPA for GitHub Pages. Fetches `data/episodes.json` and `summaries/*.md` statically. Hash routing (`#/channel/<id>`). No backend calls.
- **`site/data/episodes.json`** — Generated episode index (by `build_site.py`)
- **`site/summaries/*.md`** — Copied summary files

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
- **No Python SDK for Gemini**: Raw `urllib.request` HTTP calls.
- **Summaries as files**: Markdown files are the source of truth; `episodes.json` is derived.
- **Deduplication via SQLite**: `data/subscriptions.db` tracks processed video_ids.
