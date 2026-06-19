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
    - Local: reads youtube_token.json
    - GitHub Actions: reads YOUTUBE_TOKEN env var (JSON string, not pickle)
    """
    import base64
    creds = None

    # GitHub Actions — load token from env var (JSON format)
    token_env = os.environ.get("YOUTUBE_TOKEN")
    if token_env:
        try:
            # Try JSON first (new format)
            token_data = json.loads(base64.b64decode(token_env).decode())
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception:
            try:
                # Fallback: try raw JSON string
                token_data = json.loads(token_env)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            except Exception as e:
                print(f"❌ Could not parse YOUTUBE_TOKEN: {e}")
                sys.exit(1)

    # Local — load from JSON file
    elif os.path.exists("youtube_token.json"):
        creds = Credentials.from_authorized_user_file("youtube_token.json", SCOPES)

    # Legacy pickle support
    elif os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        print("🔄 Refreshing access token...")
        creds.refresh(Request())
        # Save refreshed token
        if not token_env:
            with open("youtube_token.json", "w") as f:
                f.write(creds.to_json())

    # No token found
    if not creds or not creds.valid:
        if not creds:
            if not os.path.exists(CLIENT_SECRETS):
                print(f"❌ No YouTube token found!")
                print(f"   Run: python youtube_auth.py")
                sys.exit(1)
            print("🔑 Opening browser for YouTube authentication...")
            flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
            with open("youtube_token.json", "w") as f:
                f.write(creds.to_json())
            print("✅ Token saved! Run: python youtube_auth.py --export")

    return build("youtube", "v3", credentials=creds)

# ── Script parsing ────────────────────────────────────────────────────────────

def extract_section(content, header):
    """
    Extract section content from script.txt.
    Finds the header line, skips the dash line, reads until next section.
    Robust — works regardless of emoji variations in header names.
    """
    lines   = content.split("\n")
    capture = False
    result  = []

    for line in lines:
        # Start capturing after header + dash line
        if header.lower() in line.lower():
            capture = True
            continue
        if capture and set(line.strip()) <= {"─", "-", "=", " ", ""}:
            if result:  # dash line after content = end of section
                break
            continue   # dash line right after header = skip it
        if capture:
            # Stop at next section header (lines with emoji + caps)
            if any(e in line for e in ["🎬","📋","#️⃣","📱","="*10]):
                break
            result.append(line)

    return "\n".join(result).strip()

def parse_script(script_path):
    """Parse script.txt and extract YouTube metadata. Robust to format variations."""
    content = open(script_path, encoding="utf-8").read()

    title    = extract_section(content, "YOUTUBE TITLE")
    desc     = extract_section(content, "YOUTUBE DESCRIPTION")
    hashtags = extract_section(content, "HASHTAGS")
    ig_cap   = extract_section(content, "INSTAGRAM CAPTION")

    # Clean title
    title = title.strip('"').strip("'").strip()

    # If description parsing failed, build from game info in header
    if not desc or len(desc) < 20:
        # Pull game info from the header block at top of script
        lines = content.split("\n")
        game_info = [l for l in lines[:8] if l.strip() and not l.startswith("=")]
        desc = "\n".join(game_info)

    # Build full description — desc + hashtags combined
    full_desc = desc.strip()
    if hashtags:
        full_desc += f"\n\n{hashtags.strip()}"
    full_desc += f"\n\n─────────────────────────"
    full_desc += f"\n🏃 {CHANNEL_NAME}"
    full_desc += f"\nSubscribe for weekly chess games, puzzles, and the slow grind of getting better."
    full_desc += f"\n{'─'*25}"

    # Parse hashtags into tag list for YouTube tags field
    tag_list = re.findall(r'#(\w+)', hashtags)
    for t in ["chess","chesscom","indianthinkingathlete","chessindia","learnchess","roadto1000"]:
        if t.lower() not in [x.lower() for x in tag_list]:
            tag_list.append(t)

    return {
        "title":       title[:100],
        "description": full_desc[:4900],
        "tags":        tag_list[:50],
    }

def get_upload_status_file(game_dir):
    return os.path.join(game_dir, "youtube_upload.json")

def get_game_type_from_script(game_dir):
    """Read game type (BLITZ/RAPID) from script.txt."""
    script = os.path.join(game_dir, "script.txt")
    if not os.path.exists(script):
        return None
    content = open(script).read()
    if "BLITZ" in content:
        return "BLITZ"
    if "RAPID" in content:
        return "RAPID"
    if "BULLET" in content:
        return "BULLET"
    return None

def add_to_playlist(youtube, video_id, playlist_id):
    """Add a video to a YouTube playlist."""
    if not playlist_id:
        return False
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind":    "youtube#video",
                        "videoId": video_id,
                    }
                }
            }
        ).execute()
        print(f"  ✅ Added to playlist")
        return True
    except Exception as e:
        print(f"  ⚠️  Playlist add failed: {e}")
        return False

def create_playlist(youtube, title, description=""):
    """Create a new playlist and return its ID."""
    try:
        resp = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title":       title,
                    "description": description,
                },
                "status": {"privacyStatus": "public"}
            }
        ).execute()
        return resp["id"]
    except Exception as e:
        print(f"  ❌ Could not create playlist: {e}")
        return None

def ensure_playlists(youtube):
    """
    Make sure BLITZ and RAPID playlists exist.
    Creates them if env vars are empty. Returns (blitz_id, rapid_id).
    """
    blitz_id = os.environ.get("PLAYLIST_BLITZ", "")
    rapid_id = os.environ.get("PLAYLIST_RAPID", "")

    if not blitz_id:
        print("  📋 Creating BLITZ playlist...")
        blitz_id = create_playlist(
            youtube,
            "Blitz Chess Games — Indian Thinking Athlete",
            "All blitz chess games from my Road to 1000 journey."
        ) or ""
        if blitz_id:
            print(f"  ✅ BLITZ playlist: {blitz_id}")
            print(f"  💡 Save as GitHub Secret: PLAYLIST_BLITZ={blitz_id}")

    if not rapid_id:
        print("  📋 Creating RAPID playlist...")
        rapid_id = create_playlist(
            youtube,
            "Rapid Chess Games — Indian Thinking Athlete",
            "All rapid chess games from my Road to 1000 journey."
        ) or ""
        if rapid_id:
            print(f"  ✅ RAPID playlist: {rapid_id}")
            print(f"  💡 Save as GitHub Secret: PLAYLIST_RAPID={rapid_id}")

    return blitz_id, rapid_id

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

def upload_video(youtube, video_path, metadata, game_dir, blitz_id="", rapid_id=""):
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

    # Add to correct playlist based on game type
    game_type = get_game_type_from_script(game_dir)
    if game_type == "BLITZ" and blitz_id:
        print(f"  📋 Adding to BLITZ playlist...")
        add_to_playlist(youtube, video_id, blitz_id)
    elif game_type == "RAPID" and rapid_id:
        print(f"  📋 Adding to RAPID playlist...")
        add_to_playlist(youtube, video_id, rapid_id)
    elif game_type:
        print(f"  ℹ️  {game_type} — no playlist ID set yet")

    save_upload_status(game_dir, video_id, metadata["title"], url)

    # Also write to persistent upload log so backfill knows this was uploaded
    log_file = "uploaded_games.json"
    try:
        existing = json.load(open(log_file)) if os.path.exists(log_file) else []
        # Store game_id: end_time_white_black
        game_id = None
        # Try to extract from game_dir name
        parts = os.path.basename(game_dir).split("_")
        if len(parts) >= 4:
            game_id = os.path.basename(game_dir)
        if game_id and game_id not in existing:
            existing.append(game_id)
            json.dump(existing, open(log_file, "w"), indent=2)
    except Exception as e:
        print(f"  ⚠️  Could not update upload log: {e}")

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
        land = os.path.join(g, "landscape.mp4")
        port = os.path.join(g, "portrait.mp4")
        scr  = os.path.join(g, "script.txt")
        if os.path.exists(land) and os.path.exists(scr):
            ready.append((g, land, port if os.path.exists(port) else None))

    if not ready:
        print(f"❌ No game folders ready for upload.")
        print(f"   Run step2 (videos) and step3 (scripts) first!")
        sys.exit(1)

    # Filter already uploaded
    to_upload = [(g,l,p) for g,l,p in ready if not already_uploaded(g)]
    skipped   = len(ready) - len(to_upload)

    if not to_upload:
        print(f"✅ All {len(ready)} games already uploaded to YouTube!")
        sys.exit(0)

    # Apply MAX_UPLOADS limit
    if MAX_UPLOADS:
        to_upload = to_upload[:MAX_UPLOADS]

    print(f"  Landscape + Portrait per game")

    print(f"🎬 YouTube Upload — {CHANNEL_NAME}")
    print(f"{'─'*55}")
    print(f"  Ready to upload: {len(to_upload)} games")
    if skipped:
        print(f"  Already uploaded: {skipped} games (skipping)")
    print(f"  Privacy: {PRIVACY_STATUS.upper()}")
    print(f"{'─'*55}\n")

    # Authenticate
    youtube = get_youtube_client()

    # Ensure playlists exist (creates if missing)
    print("📋 Checking playlists...")
    blitz_playlist, rapid_playlist = ensure_playlists(youtube)
    print()

    results = []
    for i, (game_dir, vid_path, port_path) in enumerate(to_upload):
        name = os.path.basename(game_dir)
        print(f"[{i+1:02d}/{len(to_upload)}] {name}")

        try:
            script_path = os.path.join(game_dir, "script.txt")
            metadata    = parse_script(script_path)

            if not metadata["title"]:
                # Fallback title if parsing fails
                metadata["title"] = f"Chess Game — Road to 1000 | {CHANNEL_NAME} ♟️"

            video_id = upload_video(youtube, vid_path, metadata, game_dir,
                                       blitz_playlist, rapid_playlist)
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
