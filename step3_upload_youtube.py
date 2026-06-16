"""
STEP 3 — Upload Video to YouTube
The Thinking Athlete Pipeline

Setup (one time only):
1. Go to https://console.cloud.google.com
2. Create a project → Enable "YouTube Data API v3"
3. Create OAuth 2.0 credentials → Download as client_secrets.json
4. pip install google-auth google-auth-oauthlib google-api-python-client

First run will open a browser to authenticate — after that it's automatic.
"""

import os
import sys
import json
import glob
from datetime import datetime

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print("❌ Missing Google libraries. Run:")
    print("   pip install google-auth google-auth-oauthlib google-api-python-client")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_SECRETS_FILE = "client_secrets.json"   # download from Google Console
TOKEN_FILE          = "youtube_token.json"
SCOPES              = ["https://www.googleapis.com/auth/youtube.upload"]
VIDEO_DIR           = "videos"
USERNAME            = "abhi15041984"
# ─────────────────────────────────────────────────────────────────────────────

def get_youtube_client():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print(f"❌ {CLIENT_SECRETS_FILE} not found!")
                print("   Download from: https://console.cloud.google.com → APIs → Credentials")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def build_metadata(game_data):
    """Auto-generate funny title + description from game data."""
    white = game_data["white"]["username"]
    black = game_data["black"]["username"]
    wr    = game_data["white"]["rating"]
    br    = game_data["black"]["rating"]

    # Who is Abhishek?
    if white.lower() == USERNAME.lower():
        my_rating  = wr
        opp_rating = br
        opp_name   = black
        played_as  = "White"
    else:
        my_rating  = br
        opp_rating = wr
        opp_name   = white
        played_as  = "Black"

    rating_diff = opp_rating - my_rating
    date_str    = datetime.now().strftime("%B %Y")

    if rating_diff > 0:
        title = f"I Beat Someone Rated Higher Than Me ({opp_rating} vs {my_rating}) | Road to 1000 ♟️"
        hook  = f"I am rated {my_rating}. My opponent was rated {opp_rating}.\nI won. I have no idea how. Let's review."
    else:
        title = f"Another Win on the Road to 1000 | {my_rating} Rated | {date_str} ♟️"
        hook  = f"Rated {my_rating} on chess.com. Slowly climbing. One game at a time."

    description = f"""{hook}

Playing as {played_as} against {opp_name} ({opp_rating}).

This is an auto-generated game replay from my chess.com archive.
Next stream I'll add live commentary — subscribe so you don't miss it.

💬 Can you spot where I almost threw it? Drop it in the comments.
♟️ Subscribe for weekly chess streams, puzzles, and suffering.

─────────────────────────
🏃 The Thinking Athlete
A 42-year-old developer climbing the chess.com ladder.
Road to 1000. Then 1200. One blunder at a time.
─────────────────────────

#chess #chesscom #roadto1000 #chessgame #chessreplay
#chessindia #learnchess #thinkingathlete #chessvideo #chesswin
"""
    tags = [
        "chess", "chess.com", "road to 1000", "chess replay",
        "chess india", "learn chess", "the thinking athlete",
        "chess beginner", "chess win", "chess game analysis"
    ]

    return title, description, tags

def upload_video(youtube, video_path, game_data):
    title, description, tags = build_metadata(game_data)

    print(f"📤 Uploading: {os.path.basename(video_path)}")
    print(f"   Title: {title}")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "20",   # Gaming
            "defaultLanguage": "en"
        },
        "status": {
            "privacyStatus": "private",  # ← set to "public" when ready!
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   Progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"✅ Uploaded! https://www.youtube.com/watch?v={video_id}")
    return video_id

def main():
    # Find latest video
    videos = sorted(glob.glob(os.path.join(VIDEO_DIR, "*.mp4")))
    if not videos:
        print("❌ No videos found. Run step2_generate_video.py first!")
        sys.exit(1)

    latest_video = videos[-1]
    print(f"🎬 Found video: {latest_video}")

    # Load game data
    with open("won_games.json") as f:
        games = json.load(f)
    game_data = games[0]  # matches GAME_INDEX from step2

    youtube = get_youtube_client()
    upload_video(youtube, latest_video, game_data)

    print("\n🏁 Done! Next: run step4_post_instagram.py (optional)")

if __name__ == "__main__":
    main()
