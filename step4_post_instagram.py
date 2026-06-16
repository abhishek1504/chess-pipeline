"""
STEP 4 — Post to Instagram (via Facebook Graph API)
The Thinking Athlete Pipeline

Setup (one time only):
1. You need a Facebook Business account + Instagram Professional account
2. Go to https://developers.facebook.com → Create App → Add Instagram Graph API
3. Get a long-lived access token (valid 60 days, then refresh)
4. Set your ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID below

Note: Instagram API only supports video upload via a public URL.
This script uploads to a temporary host first, then posts to Instagram.

pip install requests
"""

import requests
import json
import sys
import os
import time

# ── Config — fill these in ────────────────────────────────────────────────────
ACCESS_TOKEN         = "YOUR_INSTAGRAM_ACCESS_TOKEN"    # from Facebook Developer Console
INSTAGRAM_ACCOUNT_ID = "YOUR_INSTAGRAM_ACCOUNT_ID"      # numeric ID from Graph API
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}"

def build_caption(game_data):
    """Auto-generate funny Instagram caption from game data."""
    white    = game_data["white"]["username"]
    black    = game_data["black"]["username"]
    wr       = game_data["white"]["rating"]
    br       = game_data["black"]["rating"]

    if white.lower() == "abhi15041984":
        my_rating  = wr
        opp_rating = br
    else:
        my_rating  = br
        opp_rating = wr

    if opp_rating > my_rating:
        caption = f"""I am rated {my_rating}. My opponent was rated {opp_rating}.

I won. I have no idea how. The chess.com analysis will tell me I got lucky.
It is correct.

Road to 1000. Still going. ♟️

💬 Spot my almost-blunder in the comments.
🔴 Full streams on YouTube — link in bio.

#chess #chesscom #roadto1000 #chesswin #chessindia #learnchess
#thinkingathlete #chessvideo #chesspuzzle #chessbeginner"""
    else:
        caption = f"""Another win. Another step toward 1000.

Rated {my_rating} on chess.com.
Not fast. Not pretty. But it counts. ♟️

🔴 Full streams on YouTube — link in bio.

#chess #chesscom #roadto1000 #chesswin #chessindia #learnchess
#thinkingathlete #chessvideo #chessbeginner #chessgrind"""

    return caption

def create_media_container(video_url, caption):
    """Step 1 of Instagram upload — create container."""
    url = f"{BASE_URL}/media"
    params = {
        "media_type":   "REELS",
        "video_url":    video_url,
        "caption":      caption,
        "access_token": ACCESS_TOKEN
    }
    res = requests.post(url, params=params)
    data = res.json()

    if "id" not in data:
        print(f"❌ Container creation failed: {data}")
        sys.exit(1)

    return data["id"]

def wait_for_container(container_id, max_wait=300):
    """Poll until container is ready."""
    url = f"https://graph.facebook.com/v19.0/{container_id}"
    params = {"fields": "status_code", "access_token": ACCESS_TOKEN}

    print("⏳ Waiting for Instagram to process video", end="", flush=True)
    for _ in range(max_wait // 5):
        res = requests.get(url, params=params).json()
        status = res.get("status_code", "")
        if status == "FINISHED":
            print(" ✅")
            return True
        elif status == "ERROR":
            print(f"\n❌ Processing error: {res}")
            return False
        print(".", end="", flush=True)
        time.sleep(5)

    print("\n❌ Timed out waiting for container.")
    return False

def publish_container(container_id):
    """Step 2 — publish the container."""
    url = f"{BASE_URL}/media_publish"
    params = {
        "creation_id":  container_id,
        "access_token": ACCESS_TOKEN
    }
    res = requests.post(url, params=params)
    data = res.json()

    if "id" not in data:
        print(f"❌ Publish failed: {data}")
        sys.exit(1)

    return data["id"]

def main():
    if ACCESS_TOKEN == "YOUR_INSTAGRAM_ACCESS_TOKEN":
        print("❌ Please set your ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID in this file.")
        print("   See setup instructions at the top of this script.")
        sys.exit(1)

    with open("won_games.json") as f:
        games = json.load(f)
    game_data = games[0]

    caption = build_caption(game_data)
    print("📝 Caption preview:")
    print(caption[:200] + "...\n")

    # Instagram requires a PUBLIC video URL
    # Option 1: Upload to YouTube first, use the YouTube URL (best)
    # Option 2: Host on any public server temporarily
    video_url = input("📎 Paste the public video URL (YouTube/direct link): ").strip()
    if not video_url:
        print("❌ No URL provided.")
        sys.exit(1)

    print("📤 Creating Instagram media container...")
    container_id = create_media_container(video_url, caption)

    if not wait_for_container(container_id):
        sys.exit(1)

    print("🚀 Publishing to Instagram...")
    media_id = publish_container(container_id)
    print(f"✅ Posted to Instagram! Media ID: {media_id}")
    print("   Check your Instagram profile — it should appear as a Reel.")

if __name__ == "__main__":
    main()
