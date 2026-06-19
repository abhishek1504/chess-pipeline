# The Thinking Athlete — Chess Content Pipeline

Automated pipeline: chess.com wins → videos → YouTube

---

## Pipeline Overview

```
step1  →  step2  →  step3  →  step5
fetch     generate  scripts   upload
games     videos    metadata  to YT
```

### What each file does

| File | Purpose |
|---|---|
| `watcher.py` | Fetches TODAY's won games (last 24h) — used by daily automation |
| `backfill.py` | Fetches historical won games for a specific year/month |
| `step1_fetch_games.py` | Fetches ALL 2026 won games (manual use) |
| `step2_generate_video.py` | Generates landscape (full game) + portrait (last 20 moves) videos |
| `step3_generate_scripts.py` | Generates YouTube title, description, hashtags |
| `step5_upload_youtube.py` | Uploads both videos to YouTube, adds to playlists, cross-links |
| `youtube_auth.py` | One-time YouTube authentication |
| `sync_upload_log.py` | Syncs uploaded_games.json with existing YouTube videos |
| `manage_youtube.py` | YouTube content manager (list, dupes, delete, delete_all) |
| `uploaded_games.json` | Persistent log of uploaded games (committed to repo) |

### Quality filters (games must pass ALL to be uploaded)
- Won by actual play (no abandonment/timeout)
- Quality score >= 70 (proxy for ~70% chess.com accuracy)
  - Penalises hanging pieces, missing free captures

### Video formats
- **Landscape** (1280x720) — full game, counts toward watch hours
- **Portrait** (1080x1920) — last 20 moves, YouTube Shorts

---

## One-Time Setup (do this once)

### 1. Install dependencies
```bash
pip install chess imageio imageio-ffmpeg pillow numpy requests \
            google-auth google-auth-oauthlib google-auth-httplib2 \
            google-api-python-client
brew install ffmpeg
```

### 2. Set Anthropic API key
```bash
echo 'export ANTHROPIC_API_KEY="your-key"' >> ~/.zshrc
source ~/.zshrc
```

### 3. YouTube authentication
```bash
# Download client_secrets.json from Google Cloud Console first
python youtube_auth.py
# Browser opens → log in → Allow
python youtube_auth.py --export
# Copy output → GitHub Secret: YOUTUBE_TOKEN
```

### 4. Push to GitHub
```bash
git init
cat > .gitignore << 'IGNORE'
client_secrets.json
youtube_token.json
youtube_token.pickle
videos/
scripts/
sounds/track.aac
__pycache__/
*.pyc
won_games.json
IGNORE
git add .
git commit -m "Initial chess pipeline"
git remote add origin https://YOUR_USERNAME@github.com/YOUR_USERNAME/chess-pipeline.git
git push -u origin main
```

### 5. GitHub Secrets (Settings → Secrets → Actions)
| Secret | How to get |
|---|---|
| `YOUTUBE_TOKEN` | From `python youtube_auth.py --export` |
| `PLAYLIST_BLITZ` | Auto-created on first run, printed in logs |
| `PLAYLIST_RAPID` | Auto-created on first run, printed in logs |

---

## Daily Use

### Automatic (GitHub Actions)
- **11:00 PM IST** — daily pipeline (new wins from last 24h)
- **11:30 PM IST** — backfill auto (historical wins, 6/day, oldest first)

### Manual local run
```bash
# Fetch + generate + upload for today
python watcher.py
python step2_generate_video.py
python step3_generate_scripts.py
python step5_upload_youtube.py
```

---

## Backfill Historical Games

### Option A — Auto (recommended)
GitHub → Actions → **Chess Backfill Auto** → Run workflow
```
Year: 2026
Max uploads: 6
```
Runs daily until all 2026 games are uploaded chronologically.

### Option B — Manual month by month
```bash
python backfill.py 2026 01   # January
python step2_generate_video.py
python step3_generate_scripts.py
python step5_upload_youtube.py
```

---

## Fresh Start (delete all YouTube content)

```bash
python manage_youtube.py delete_all
# Type 'DELETE ALL' to confirm
# This also resets uploaded_games.json

git add uploaded_games.json
git commit -m "Fresh start"
git push origin main
```

---

## Content Management

```bash
python manage_youtube.py list        # list all videos
python manage_youtube.py dupes       # find duplicates
python manage_youtube.py cleanup     # interactive cleanup
python manage_youtube.py delete_all  # delete everything
python sync_upload_log.py            # sync log with YouTube
```

---

## Sounds (put in sounds/ folder)
| File | Used for |
|---|---|
| `move1.mp3` | Normal move |
| `capture.mp3` | Piece capture |
| `castle.mp3` | Castling |
| `promote.mp3` | Pawn promotion |

---

## Adjusting Quality Filter
Edit `MIN_QUALITY` in `backfill.py` and `step1_fetch_games.py`:
```python
MIN_QUALITY = 70   # 70 = strict, 60 = lenient, 50 = very lenient
```
