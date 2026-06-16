"""
STEP 5 — Automated YouTube Upload
The Thinking Athlete Pipeline

Reads each game folder, extracts title/description/hashtags from script.txt,
and uploads landscape.mp4 to YouTube as a private video.

Setup (one time):
1. Go to https://console.cloud.google.com
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop app) → download client_secrets.json
4. pip install google-auth google-auth-oauthlib google-api-python-client
5. Run this script once — browser opens for auth → token saved automatically

Requirements:
    pip install google-auth google-auth-oauthlib google-api-python-client
"""

import os
import sys
import re
import json
import glob
import time
import pickle
from datetime import datetime
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Run: pip install google-auth google-auth-oauthlib google-api-python-client")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
VIDEOS_DIR        = "videos"
CLIENT_SECRETS    = "client_secrets.json"
TOKEN_FILE        = "youtube_token.pickle"
SCOPES            = ["https://www.googleapis.com/auth/youtube.upload",
                     "https://www.googleapis.com/auth/youtube"]
PRIVACY_STATUS    = "private"    # "private" → review → change to "public" manually
                                 # change to "public" to upload directly public
CATEGORY_ID       = "20"        # Gaming
DEFAULT_LANGUAGE  = "en"
CHANNEL_NAME      = "Indian Thinking Athlete"
MAX_UPLOADS       = None         # None = upload all, set to 5 to limit
# ─────────────────────────────────────────────────────────────────────────────

MONTH_NAMES = {
    "01":"January","02":"February","03":"March","04":"April",
    "05":"May","06":"June","07":"July","08":"August",
    "09":"September","10":"October","11":"November","12":"December"
}

def get_youtube_client():
    """
    Authenticate and return YouTube API client.
    - Local: reads youtube_token.pickle
    - GitHub Actions: reads YOUTUBE_TOKEN env var (base64 encoded pickle)
    """
    import base64
    creds = None

    # GitHub Actions — load token from env var
    token_b64 = os.environ.get("YOUTUBE_TOKEN")
    if token_b64:
        creds = pickle.loads(base64.b64decode(token_b64))

    # Local — load from pickle file
    elif os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        print("🔄 Refreshing access token...")
        creds.refresh(Request())
        # Save refreshed token locally if running locally
        if not token_b64 and os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)

    # No token found — need to auth
    if not creds:
        if not os.path.exists(CLIENT_SECRETS):
            print(f"❌ No YouTube token found!")
            print(f"   Run: python youtube_auth.py")
            sys.exit(1)
        print("🔑 Opening browser for YouTube authentication...")
        flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
        print("✅ Token saved! Run: python youtube_auth.py --export")
        print("   to export for GitHub Actions.")

    return build("youtube", "v3", credentials=creds)

# ── Script parsing ────────────────────────────────────────────────────────────

def extract_section(content, header, next_header=None):
    """Extract a section from script.txt between header and next_header."""
    pattern = rf"{re.escape(header)}\n─+\n(.*?)"
    if next_header:
        pattern += rf"(?=\n\n{re.escape(next_header)})"
    else:
        pattern += r"$"
    match = re.search(pattern, content, re.DOTALL)
    return match.group(1).strip() if match else ""

def parse_script(script_path):
    """Parse script.txt and extract YouTube metadata."""
    content = open(script_path, encoding="utf-8").read()

    title = extract_section(content, "🎬 YOUTUBE TITLE",   "📋 YOUTUBE DESCRIPTION")
    desc  = extract_section(content, "📋 YOUTUBE DESCRIPTION", "#️⃣  YOUTUBE HASHTAGS")
    tags  = extract_section(content, "#️⃣  YOUTUBE HASHTAGS",  "📱 INSTAGRAM CAPTION")

    # Clean title — remove quotes if Claude wrapped it
    title = title.strip('"').strip("'").strip()

    # Parse hashtags into list
    tag_list = re.findall(r'#(\w+)', tags)
    # Add default tags always
    for t in ["chess","chesscom","indianthinkingathlete","chessindia","learnchess"]:
        if t not in tag_list:
            tag_list.append(t)

    # Build full description with hashtags appended
    full_desc = desc
    if tags:
        full_desc += f"\n\n{tags}"
    full_desc += f"\n\n─────────────────────────\n🏃 {CHANNEL_NAME}\nSubscribe for weekly chess games, puzzles, and the slow grind of getting better.\n─────────────────────────"

    return {
        "title":       title[:100],   # YouTube title max 100 chars
        "description": full_desc[:5000],  # YouTube desc max 5000 chars
        "tags":        tag_list[:500],    # YouTube tags max 500 chars total
    }

def get_upload_status_file(game_dir):
    return os.path.join(game_dir, "youtube_upload.json")

def already_uploaded(game_dir):
    """Check if this game was already uploaded."""
    status_file = get_upload_status_file(game_dir)
    if os.path.exists(status_file):
        data = json.load(open(status_file))
        return data.get("video_id") is not None
    return False

def save_upload_status(game_dir, video_id, title, url):
    """Save upload info so we don't re-upload."""
    status = {
        "video_id":   video_id,
        "title":      title,
        "url":        url,
        "uploaded_at": datetime.now().isoformat(),
        "privacy":    PRIVACY_STATUS,
    }
    with open(get_upload_status_file(game_dir), "w") as f:
        json.dump(status, f, indent=2)

def upload_video(youtube, video_path, metadata, game_dir):
    """Upload video to YouTube with retry on quota errors."""
    print(f"  📤 Uploading: {os.path.basename(video_path)}")
    print(f"  📌 Title: {metadata['title']}")
    print(f"  🔒 Privacy: {PRIVACY_STATUS}")

    body = {
        "snippet": {
            "title":          metadata["title"],
            "description":    metadata["description"],
            "tags":           metadata["tags"],
            "categoryId":     CATEGORY_ID,
            "defaultLanguage": DEFAULT_LANGUAGE,
        },
        "status": {
            "privacyStatus":          PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
            "madeForKids":             False,
        }
    }

    media = MediaFileUpload(
        video_path,
        chunksize=5 * 1024 * 1024,   # 5MB chunks
        resumable=True,
        mimetype="video/mp4"
    )

    request  = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response  = None
    retries   = 0
    max_retries = 5

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"  ⏳ Progress: {pct}%", end="\r")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504] and retries < max_retries:
                retries += 1
                wait = 2 ** retries
                print(f"  ⚠️  HTTP {e.resp.status} — retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise

    video_id = response["id"]
    url      = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n  ✅ Uploaded! {url}")
    print(f"  🔒 Status: {PRIVACY_STATUS} — review and make public when ready")

    save_upload_status(game_dir, video_id, metadata["title"], url)
    return video_id

def print_summary(results):
    """Print upload summary at end."""
    print(f"\n{'═'*55}")
    print(f"📊 UPLOAD SUMMARY")
    print(f"{'═'*55}")
    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f"  {status} {r['name']}")
        if r["success"]:
            print(f"      {r['url']}")
        else:
            print(f"      Error: {r['error']}")
    print(f"{'═'*55}")
    print(f"  Uploaded: {sum(1 for r in results if r['success'])}/{len(results)}")
    if PRIVACY_STATUS == "private":
        print(f"\n💡 All videos are PRIVATE — review in YouTube Studio,")
        print(f"   then change to Public when you're happy with them.")
        print(f"   studio.youtube.com → Content → change visibility")

def main():
    # Find all game folders with landscape.mp4 + script.txt
    game_folders = sorted(glob.glob(os.path.join(VIDEOS_DIR, "*", "*", "game_*")))

    ready = []
    for g in game_folders:
        # Prefer landscape_final.mp4 (with audio) else landscape.mp4
        vid = os.path.join(g, "landscape_final.mp4")
        if not os.path.exists(vid):
            vid = os.path.join(g, "landscape.mp4")
        scr = os.path.join(g, "script.txt")
        if os.path.exists(vid) and os.path.exists(scr):
            ready.append((g, vid))

    if not ready:
        print(f"❌ No game folders ready for upload.")
        print(f"   Run step2 (videos) and step3 (scripts) first!")
        sys.exit(1)

    # Filter already uploaded
    to_upload = [(g,v) for g,v in ready if not already_uploaded(g)]
    skipped   = len(ready) - len(to_upload)

    if not to_upload:
        print(f"✅ All {len(ready)} games already uploaded to YouTube!")
        sys.exit(0)

    # Apply MAX_UPLOADS limit
    if MAX_UPLOADS:
        to_upload = to_upload[:MAX_UPLOADS]

    print(f"🎬 YouTube Upload — {CHANNEL_NAME}")
    print(f"{'─'*55}")
    print(f"  Ready to upload: {len(to_upload)} games")
    if skipped:
        print(f"  Already uploaded: {skipped} games (skipping)")
    print(f"  Privacy: {PRIVACY_STATUS.upper()}")
    print(f"{'─'*55}\n")

    # Authenticate
    youtube = get_youtube_client()

    results = []
    for i, (game_dir, vid_path) in enumerate(to_upload):
        name = os.path.basename(game_dir)
        print(f"[{i+1:02d}/{len(to_upload)}] {name}")

        try:
            script_path = os.path.join(game_dir, "script.txt")
            metadata    = parse_script(script_path)

            if not metadata["title"]:
                # Fallback title if parsing fails
                metadata["title"] = f"Chess Game — Road to 1000 | {CHANNEL_NAME} ♟️"

            video_id = upload_video(youtube, vid_path, metadata, game_dir)
            url      = f"https://www.youtube.com/watch?v={video_id}"
            results.append({"name": name, "success": True, "url": url, "error": None})

            # Small delay between uploads to avoid quota issues
            if i < len(to_upload) - 1:
                print(f"  ⏸️  Waiting 3s before next upload...")
                time.sleep(3)

        except HttpError as e:
            error = f"YouTube API error: {e.resp.status} — {e.content.decode()[:200]}"
            print(f"  ❌ {error}")
            results.append({"name": name, "success": False, "url": None, "error": error})

            # Quota exceeded — stop uploading
            if e.resp.status == 403:
                print(f"\n⚠️  Quota likely exceeded. YouTube allows ~6 uploads/day.")
                print(f"   Try again tomorrow or upgrade your API quota.")
                break

        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append({"name": name, "success": False, "url": None, "error": str(e)})

        print()

    print_summary(results)

if __name__ == "__main__":
    main()
