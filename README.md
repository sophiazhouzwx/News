# Daily AI News

A personal bilingual (EN/CN) web app that delivers a daily AI and tech news digest, auto-summarized podcast episodes, and Red Note (小红书) livestream replay summaries every morning, with on-demand video/podcast summarization — powered by Anthropic Claude.

## Features

- **Daily News Digest** — Aggregates top stories from Hacker News, TechCrunch, The Verge, Ars Technica, MIT Technology Review, Reddit, and more. Summarized into a structured bilingual digest by Claude.
- **Podcast Auto-Summarization** — Tracks 5 podcasts via RSS (WSJ Tech News Briefing, WSJ What's News, NPR Up First, 天真不天真, 半拿铁｜商业浮沉录), downloads new episodes, transcribes with Whisper, and summarizes bilingually.
- **Livestream Summaries** — Tracks Red Note (小红书) accounts for new video/livestream replay posts via RSSHub, downloads with yt-dlp, transcribes with Whisper, and summarizes bilingually. Also supports manual URL submission.
- **On-Demand Media Summarization** — Paste any YouTube, podcast, or audio URL to get a bilingual summary.
- **Push Notifications** — Web Push notifications when the daily digest is ready (includes livestream count).
- **Bilingual** — All content available in both English and Chinese with a one-click toggle.
- **Dark Mode** — Full dark mode support.

## Architecture

```
Backend:  Python 3.12 + FastAPI + SQLAlchemy + SQLite
Frontend: React 18 + Vite + Tailwind CSS
AI:       Anthropic Claude API
Audio:    yt-dlp + OpenAI Whisper (local)
Scheduler: APScheduler (in-process cron)
Push:     Web Push via pywebpush + VAPID
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- ffmpeg (required by Whisper for audio processing)
- yt-dlp CLI (installed via pip or standalone)

## Setup

### 1. Clone and configure

```bash
cd daily-ai-news/backend
cp .env.example .env
# Edit .env with your API keys
```

Required environment variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `REDDIT_CLIENT_ID` | Reddit app client ID (optional — Reddit sources skipped if empty) |
| `REDDIT_CLIENT_SECRET` | Reddit app client secret (optional) |
| `VAPID_PRIVATE_KEY` | VAPID private key for Web Push (generate with `vapid --gen`) |
| `VAPID_PUBLIC_KEY` | VAPID public key |
| `VAPID_CONTACT_EMAIL` | Your email for VAPID claims |
| `DIGEST_HOUR` | Hour to run daily digest (default: 7) |
| `DIGEST_MINUTE` | Minute to run daily digest (default: 0) |
| `XIAOHONGSHU_COOKIE` | Xiaohongshu login cookie for RSSHub fulltext (optional -- basic tracking works without it) |
| `RSSHUB_BASE_URL` | RSSHub instance URL (default: `https://rsshub.app`) |

### 2. Generate VAPID keys

```bash
pip install py-vapid
vapid --gen
# Copy the private and public keys to your .env
```

### 3. Install backend dependencies

```bash
cd daily-ai-news/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Install frontend dependencies

```bash
cd daily-ai-news/frontend
npm install
```

## Running

### Start the backend

```bash
cd daily-ai-news/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Start the frontend (dev)

```bash
cd daily-ai-news/frontend
npm run dev
```

The frontend runs on `http://localhost:5173` and proxies API requests to the backend on port 8000.

### Trigger a digest manually

You can trigger the daily digest job via the Python shell:

```python
from app.services.scheduler import daily_digest_job
daily_digest_job()
```

## Tracked Podcasts

| Podcast | Schedule | Language |
|---------|----------|----------|
| WSJ Tech News Briefing | Daily | English |
| WSJ What's News | Twice daily | English |
| NPR Up First | Daily | English |
| 天真不天真 | Biweekly | Chinese |
| 半拿铁｜商业浮沉录 | Weekly | Chinese |

To add more podcasts, edit the `TRACKED_PODCASTS` list in `backend/app/config.py`.

## Tracked Red Note Accounts (Livestreams)

| Account | Language | Notes |
|---------|----------|-------|
| xb99681 | Chinese | Auto-tracked via RSSHub; also supports manual URL submission |

To add more accounts, edit the `TRACKED_REDNOTE_ACCOUNTS` list in `backend/app/config.py`.

**How it works:** The daily scheduler polls each account's RSSHub RSS feed for new video posts. New videos are downloaded with yt-dlp, transcribed with Whisper (medium model for Chinese), and summarized bilingually by Claude. You can also manually paste any `xiaohongshu.com/explore/...` URL on the Livestreams page.

**Important:** RSSHub's Xiaohongshu route may require a `XIAOHONGSHU_COOKIE` env var for reliable access. If the auto-tracking doesn't pick up livestream replays (some creators don't post them as regular notes), use the manual URL submission as a fallback.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/digests` | List daily digests |
| GET | `/api/digests/latest` | Get latest digest |
| GET | `/api/digests/{id}` | Get specific digest |
| GET | `/api/podcasts` | List tracked podcasts |
| GET | `/api/podcasts/{name}/episodes` | List episodes for a podcast |
| GET | `/api/podcasts/episodes/{id}` | Get episode detail |
| GET | `/api/livestreams` | List livestream summaries (optional `?account=` filter) |
| GET | `/api/livestreams/accounts` | List tracked Red Note accounts |
| GET | `/api/livestreams/{id}` | Get specific livestream summary |
| POST | `/api/livestreams/summarize` | Submit Red Note replay URL |
| POST | `/api/media/summarize` | Submit URL for summarization |
| GET | `/api/media` | List media summaries |
| GET | `/api/media/{id}` | Get media summary |
| POST | `/api/push/subscribe` | Register push subscription |
| DELETE | `/api/push/subscribe` | Remove push subscription |
| GET | `/api/push/vapid-public-key` | Get VAPID public key |
