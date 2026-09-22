"""
longform_upload_youtube.py — Upload Monthly Compilation to YouTube
The Thinking Athlete Pipeline — Long-Form Content

Uploads compilation.mp4 as a private long-form YouTube video.
Reads title/description/hashtags from script.txt.

Usage:
    python longform_upload_youtube.py --year 2026 --month 1
"""

import os
import sys
import re
import json
import time
import argparse
from datetime import datetime

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

OUTPUT_DIR     = "longform"
CLIENT_SECRETS = "client_secrets.json"
TOKEN_FILE     = "youtube_token.json"
SCOPES         = ["https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube"]
PRIVACY_STATUS = "private"
CATEGORY_ID    = "20"    # Gaming
NEXT_MILESTONE = int(os.environ.get("NEXT_MILESTONE", "1200"))

MONTH_NAMES = {
    1:"01_January", 2:"02_February", 3:"03_March", 4:"04_April",
    5:"05_May",     6:"06_June",     7:"07_July",  8:"08_August",
    9:"09_September",10:"10_October",11:"11_November",12:"12_December",
}


def get_youtube_client():
    import base64
    creds = None

    token_env = os.environ.get("YOUTUBE_TOKEN")
    if token_env:
        try:
            token_data = json.loads(base64.b64decode(token_env).decode())
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception:
            try:
                token_data = json.loads(token_env)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            except Exception as e:
                print(f"❌ Could not parse YOUTUBE_TOKEN: {e}")
                sys.exit(1)
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        print("🔄 Refreshing access token...")
        creds.refresh(Request())
        if not token_env:
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())

    if not creds or not creds.valid:
        if not creds:
            if not os.path.exists(CLIENT_SECRETS):
                print("❌ No YouTube token found!  Run: python youtube_auth.py")
                sys.exit(1)
            flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            print("✅ Token saved!")

    return build("youtube", "v3", credentials=creds)


def parse_script(script_path):
    content = open(script_path, encoding="utf-8").read()

    def extract(header):
        lines   = content.split("\n")
        capture = False
        result  = []
        for line in lines:
            if header.lower() in line.lower():
                capture = True
                continue
            if capture:
                s = line.strip()
                if s and set(s) <= {"─", "-", "="}:
                    if result:
                        break
                    continue
                if any(e in line for e in ["🎬","📋","#️⃣","🖼️","📌","="*10]):
                    break
                result.append(line)
        return "\n".join(result).strip()

    title    = extract("YOUTUBE TITLE").strip('"').strip("'")
    desc     = extract("YOUTUBE DESCRIPTION")
    hashtags = extract("HASHTAGS")
    tag_list = re.findall(r'#(\w+)', hashtags)

    for t in ["chess", "chesscom", "indianthinkingathlete",
              f"roadto{NEXT_MILESTONE}", "chessindia"]:
        if t.lower() not in [x.lower() for x in tag_list]:
            tag_list.append(t)

    full_desc = desc.strip()
    if hashtags:
        full_desc += f"\n\n{hashtags.strip()}"

    return {
        "title":       title[:100],
        "description": full_desc[:4900],
        "tags":        tag_list[:50],
    }


def upload_video(youtube, video_path, metadata):
    print(f"  📤 Uploading: {os.path.basename(video_path)}")
    print(f"  📌 Title: {metadata['title']}")
    print(f"  🔒 Privacy: {PRIVACY_STATUS}")
    sz = os.path.getsize(video_path) / 1024 / 1024
    print(f"  📦 Size: {sz:.1f} MB")

    body = {
        "snippet": {
            "title":           metadata["title"],
            "description":     metadata["description"],
            "tags":            metadata["tags"],
            "categoryId":      CATEGORY_ID,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":           PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
            "madeForKids":             False,
        },
    }
    media   = MediaFileUpload(video_path, chunksize=10*1024*1024,
                               resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media)

    response = None
    retries  = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  ⏳ {int(status.progress()*100)}%", end="\r")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504] and retries < 5:
                retries += 1
                time.sleep(2 ** retries)
            else:
                raise

    video_id = response["id"]
    url      = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n  ✅ Uploaded: {url}")
    return video_id, url


def main():
    year  = int(os.environ.get("YEAR",  0) or 0)
    month = int(os.environ.get("MONTH", 0) or 0)

    parser = argparse.ArgumentParser()
    parser.add_argument("--year",  type=int)
    parser.add_argument("--month", type=int)
    args, _ = parser.parse_known_args()

    if args.year:  year  = args.year
    if args.month: month = args.month

    if not year or not month:
        print("❌ Provide --year and --month")
        sys.exit(1)

    out_dir     = os.path.join(OUTPUT_DIR, str(year), MONTH_NAMES[month])
    video_path  = os.path.join(out_dir, "compilation.mp4")
    script_path = os.path.join(out_dir, "script.txt")
    upload_json = os.path.join(out_dir, "youtube_upload.json")

    if not os.path.exists(video_path):
        print(f"❌ {video_path} not found — run longform_generate_video.py first!")
        sys.exit(1)
    if not os.path.exists(script_path):
        print(f"❌ {script_path} not found — run longform_generate_script.py first!")
        sys.exit(1)

    # Skip if already uploaded
    if os.path.exists(upload_json):
        info = json.load(open(upload_json))
        if info.get("video_id"):
            print(f"✅ Already uploaded: {info['url']}")
            sys.exit(0)

    month_str = datetime(year, month, 1).strftime("%B %Y")
    print(f"🎬 Uploading {month_str} compilation to YouTube")
    print(f"{'─'*55}")

    metadata = parse_script(script_path)
    youtube  = get_youtube_client()

    try:
        video_id, url = upload_video(youtube, video_path, metadata)
    except HttpError as e:
        if e.resp.status == 403:
            print(f"\n⚠️  Quota exceeded — try again tomorrow.")
        else:
            print(f"\n❌ YouTube API error: {e.resp.status}")
        sys.exit(1)

    info = {
        "video_id":    video_id,
        "url":         url,
        "title":       metadata["title"],
        "uploaded_at": datetime.now().isoformat(),
        "privacy":     PRIVACY_STATUS,
        "year":        year,
        "month":       month,
    }
    with open(upload_json, "w") as f:
        json.dump(info, f, indent=2)

    print(f"\n🏁 Done!")
    print(f"   URL:   {url}")
    print(f"   Status: {PRIVACY_STATUS.upper()} — review in YouTube Studio and publish when ready")
    print(f"   studio.youtube.com → Content → change visibility")


if __name__ == "__main__":
    main()
