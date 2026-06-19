"""
sync_upload_log.py — Sync uploaded_games.json with your YouTube channel
The Thinking Athlete Pipeline

Fetches all videos from your YouTube channel, matches them to game folders,
and populates uploaded_games.json so backfill won't re-upload them.

Run this ONCE to backfill the upload log with existing videos.

Usage:
    python sync_upload_log.py
"""

import os
import sys
import json
import re
from datetime import datetime

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("❌ Run: pip install google-auth google-auth-oauthlib google-api-python-client")
    sys.exit(1)

TOKEN_FILE     = "youtube_token.json"
CLIENT_SECRETS = "client_secrets.json"
SCOPES         = ["https://www.googleapis.com/auth/youtube.readonly"]
UPLOAD_LOG     = "uploaded_games.json"
VIDEOS_DIR     = "videos"

MONTH_NAMES = {
    1:"01_January",  2:"02_February", 3:"03_March",    4:"04_April",
    5:"05_May",      6:"06_June",     7:"07_July",      8:"08_August",
    9:"09_September",10:"10_October", 11:"11_November", 12:"12_December"
}

def get_youtube():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def get_all_channel_videos(youtube):
    """Fetch all video titles from the channel."""
    videos   = []
    page_tok = None
    print("📡 Fetching all videos from your YouTube channel...")

    while True:
        resp = youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            maxResults=50,
            pageToken=page_tok,
        ).execute()

        for item in resp.get("items", []):
            videos.append({
                "id":        item["id"]["videoId"],
                "title":     item["snippet"]["title"],
                "published": item["snippet"]["publishedAt"],
            })

        page_tok = resp.get("nextPageToken")
        if not page_tok:
            break

    print(f"✅ Found {len(videos)} videos on YouTube\n")
    return videos

def get_local_game_folders():
    """Find all game folders under videos/."""
    folders = []
    if not os.path.exists(VIDEOS_DIR):
        return folders
    for year in os.listdir(VIDEOS_DIR):
        year_path = os.path.join(VIDEOS_DIR, year)
        if not os.path.isdir(year_path): continue
        for month in os.listdir(year_path):
            month_path = os.path.join(year_path, month)
            if not os.path.isdir(month_path): continue
            for game in os.listdir(month_path):
                game_path = os.path.join(month_path, game)
                if os.path.isdir(game_path) and game.startswith("game_"):
                    folders.append(game)
    return folders

def normalise(text):
    """Normalise text for fuzzy matching."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = ' '.join(text.split())
    return text

def match_video_to_folder(video_title, folders):
    """
    Try to match a YouTube video title to a local game folder name.
    e.g. 'Sicilian Defense | BLITZ | Abhi vs xyz' → 'game_001_xyz_vs_Abhi15041984'
    """
    norm_title = normalise(video_title)

    for folder in folders:
        # Extract player names from folder: game_001_WHITE_vs_BLACK
        parts = folder.split("_")
        if len(parts) < 4: continue

        # Find 'vs' index
        try:
            vs_idx = parts.index("vs")
            white  = "_".join(parts[2:vs_idx]).lower()
            black  = "_".join(parts[vs_idx+1:]).lower()
        except ValueError:
            continue

        # Check if either player name appears in the video title
        if white in norm_title or black in norm_title:
            return folder

    return None

def main():
    # Load existing upload log
    existing = []
    if os.path.exists(UPLOAD_LOG):
        try:
            existing = json.load(open(UPLOAD_LOG))
            print(f"📋 Current upload log: {len(existing)} entries")
        except:
            existing = []

    existing_set = set(existing)

    # Get YouTube videos
    youtube = get_youtube()
    yt_videos = get_all_channel_videos(youtube)

    # Get local game folders
    local_folders = get_local_game_folders()
    print(f"📂 Local game folders found: {len(local_folders)}")

    # Strategy 1: Match by player name in title
    matched   = []
    unmatched = []

    for v in yt_videos:
        folder = match_video_to_folder(v["title"], local_folders)
        if folder:
            matched.append((v, folder))
        else:
            unmatched.append(v)

    print(f"\n✅ Matched {len(matched)} videos to local folders")
    print(f"⚠️  Unmatched: {len(unmatched)} videos\n")

    # Strategy 2: For unmatched videos, add by video ID
    # These are videos uploaded before local folders existed
    added = 0
    for v, folder in matched:
        if folder not in existing_set:
            existing.append(folder)
            existing_set.add(folder)
            added += 1
            print(f"  ✅ Logged: {folder}")
            print(f"     Title:  {v['title'][:60]}")

    # For unmatched — add by video ID as fallback
    for v in unmatched:
        vid_key = f"yt_{v['id']}"
        if vid_key not in existing_set:
            existing.append(vid_key)
            existing_set.add(vid_key)
            added += 1
            print(f"  ✅ Logged by ID: {v['id']}")
            print(f"     Title: {v['title'][:60]}")

    # Save
    with open(UPLOAD_LOG, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"\n{'─'*55}")
    print(f"📊 Summary:")
    print(f"   Videos on YouTube:     {len(yt_videos)}")
    print(f"   Matched to folders:    {len(matched)}")
    print(f"   Added to upload log:   {added}")
    print(f"   Total in log now:      {len(existing)}")
    print(f"{'─'*55}")
    print(f"\n✅ uploaded_games.json updated!")
    print(f"   Commit this file to GitHub so backfill skips these games:")
    print(f"   git add uploaded_games.json")
    print(f"   git commit -m 'Sync upload log with existing YouTube videos'")
    print(f"   git push origin main")

if __name__ == "__main__":
    main()
