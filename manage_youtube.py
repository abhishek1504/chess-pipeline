"""
manage_youtube.py — YouTube Content Manager
The Thinking Athlete Pipeline

Commands:
    python manage_youtube.py list              — list all uploaded videos
    python manage_youtube.py dupes            — find duplicate videos
    python manage_youtube.py delete <video_id> — delete a specific video
    python manage_youtube.py cleanup          — interactive duplicate cleanup
    python manage_youtube.py delete_all       — delete ALL videos (fresh start)

Requirements:
    pip install google-auth google-auth-oauthlib google-api-python-client
"""

import os
import sys
import json
import pickle
import re
from datetime import datetime
from collections import defaultdict

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Run: pip install google-auth google-auth-oauthlib google-api-python-client")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_SECRETS = "client_secrets.json"
TOKEN_FILE     = "youtube_token.json"
SCOPES         = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
CHANNEL_NAME   = "Indian Thinking Athlete"
# ─────────────────────────────────────────────────────────────────────────────

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

def get_all_videos(youtube):
    """Fetch all videos from the channel."""
    videos   = []
    page_tok = None

    print("📡 Fetching all videos from your channel...")

    while True:
        resp = youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            maxResults=50,
            pageToken=page_tok,
        ).execute()

        for item in resp.get("items", []):
            vid_id  = item["id"]["videoId"]
            snippet = item["snippet"]
            videos.append({
                "id":           vid_id,
                "title":        snippet.get("title", ""),
                "published":    snippet.get("publishedAt", ""),
                "description":  snippet.get("description", "")[:100],
                "url":          f"https://www.youtube.com/watch?v={vid_id}",
                "thumbnail":    snippet.get("thumbnails",{}).get("default",{}).get("url",""),
            })

        page_tok = resp.get("nextPageToken")
        if not page_tok:
            break

    # Get extra details (privacy status, duration)
    if videos:
        ids   = [v["id"] for v in videos]
        # Fetch in batches of 50
        for i in range(0, len(ids), 50):
            batch = ids[i:i+50]
            detail = youtube.videos().list(
                part="status,contentDetails,statistics",
                id=",".join(batch)
            ).execute()

            detail_map = {d["id"]: d for d in detail.get("items", [])}
            for v in videos:
                if v["id"] in detail_map:
                    d = detail_map[v["id"]]
                    v["privacy"]  = d.get("status",{}).get("privacyStatus","unknown")
                    v["views"]    = d.get("statistics",{}).get("viewCount","0")
                    v["likes"]    = d.get("statistics",{}).get("likeCount","0")
                    v["duration"] = d.get("contentDetails",{}).get("duration","")

    print(f"✅ Found {len(videos)} videos\n")
    return videos

def extract_game_key(title):
    """
    Extract a normalised key from video title to detect duplicates.
    Strips rating, date, episode numbers — keeps opening + players.
    e.g. 'Sicilian Defense | BLITZ | Beat 163 pts | 946' → 'siciliandefense_blitz'
    """
    title = title.lower()
    # Remove ratings, move counts, dates
    title = re.sub(r'\d{3,4}\s*(rated|pts|moves|♟)', '', title)
    title = re.sub(r'road to \d+', '', title)
    title = re.sub(r'[^a-z\s]', '', title)
    title = ' '.join(title.split())
    # Keep first 4 significant words
    words = [w for w in title.split() if len(w) > 2][:4]
    return '_'.join(words)

def find_dupes(videos):
    """Group videos by normalised title key to find duplicates."""
    groups = defaultdict(list)
    for v in videos:
        key = extract_game_key(v["title"])
        groups[key].append(v)
    return {k: vs for k, vs in groups.items() if len(vs) > 1}

def fmt_date(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z","+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return iso

def cmd_list(youtube):
    """List all videos on the channel."""
    videos = get_all_videos(youtube)
    if not videos:
        print("No videos found.")
        return

    print(f"{'─'*80}")
    print(f"{'#':<4} {'TITLE':<45} {'PRIVACY':<10} {'VIEWS':<8} {'DATE'}")
    print(f"{'─'*80}")
    for i, v in enumerate(videos, 1):
        title   = v["title"][:43] + ".." if len(v["title"]) > 45 else v["title"]
        privacy = v.get("privacy","?")
        views   = v.get("views","0")
        date    = fmt_date(v.get("published",""))
        print(f"{i:<4} {title:<45} {privacy:<10} {views:<8} {date}")
        print(f"     {v['url']}")
    print(f"{'─'*80}")
    print(f"Total: {len(videos)} videos")

def cmd_dupes(youtube):
    """Find and display duplicate videos."""
    videos = get_all_videos(youtube)
    dupes  = find_dupes(videos)

    if not dupes:
        print("✅ No duplicate videos found!")
        return

    print(f"⚠️  Found {len(dupes)} groups of potential duplicates:\n")
    print(f"{'═'*80}")

    total_dupes = 0
    for key, group in sorted(dupes.items()):
        print(f"\n🔴 DUPLICATE GROUP: [{key}]")
        print(f"{'─'*80}")

        # Sort by date — oldest first
        group.sort(key=lambda x: x.get("published",""))

        for i, v in enumerate(group):
            marker  = "  KEEP →" if i == len(group)-1 else "DELETE →"
            privacy = v.get("privacy","?")
            views   = v.get("views","0")
            date    = fmt_date(v.get("published",""))
            print(f"\n  {marker}")
            print(f"  Title:   {v['title']}")
            print(f"  URL:     {v['url']}")
            print(f"  ID:      {v['id']}")
            print(f"  Privacy: {privacy}  |  Views: {views}  |  Date: {date}")

        total_dupes += len(group) - 1  # keep newest, delete rest

    print(f"\n{'═'*80}")
    print(f"📊 Summary:")
    print(f"   Duplicate groups:  {len(dupes)}")
    print(f"   Videos to delete:  {total_dupes}")
    print(f"   Videos to keep:    {len(videos) - total_dupes}")
    print(f"\n💡 To delete a video:")
    print(f"   python manage_youtube.py delete <VIDEO_ID>")
    print(f"\n💡 To delete all duplicates interactively:")
    print(f"   python manage_youtube.py cleanup")

    # Save report to file
    report_path = "duplicate_report.txt"
    with open(report_path, "w") as f:
        f.write(f"Duplicate Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Channel: {CHANNEL_NAME}\n")
        f.write(f"{'='*80}\n\n")
        for key, group in sorted(dupes.items()):
            group.sort(key=lambda x: x.get("published",""))
            f.write(f"GROUP: [{key}]\n")
            for i, v in enumerate(group):
                action = "KEEP" if i == len(group)-1 else "DELETE"
                f.write(f"  [{action}] {v['title']}\n")
                f.write(f"         {v['url']}\n")
                f.write(f"         ID: {v['id']} | Views: {v.get('views','0')} | {fmt_date(v.get('published',''))}\n")
            f.write("\n")
    print(f"\n📄 Full report saved to: {report_path}")

def cmd_delete(youtube, video_id):
    """Delete a single video by ID."""
    # First show what we're deleting
    try:
        resp = youtube.videos().list(part="snippet,status", id=video_id).execute()
        if not resp.get("items"):
            print(f"❌ Video not found: {video_id}")
            return

        v       = resp["items"][0]
        title   = v["snippet"]["title"]
        privacy = v["status"]["privacyStatus"]
        print(f"\n⚠️  About to delete:")
        print(f"   Title:   {title}")
        print(f"   ID:      {video_id}")
        print(f"   Privacy: {privacy}")
        print(f"   URL:     https://www.youtube.com/watch?v={video_id}")

        confirm = input("\nType 'yes' to confirm delete: ").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

        youtube.videos().delete(id=video_id).execute()
        print(f"✅ Deleted: {title}")

    except HttpError as e:
        print(f"❌ Error: {e}")

def cmd_cleanup(youtube):
    """Interactive cleanup — shows each duplicate group and asks what to delete."""
    videos = get_all_videos(youtube)
    dupes  = find_dupes(videos)

    if not dupes:
        print("✅ No duplicates found!")
        return

    deleted = 0
    skipped = 0

    for key, group in sorted(dupes.items()):
        group.sort(key=lambda x: x.get("published",""))
        print(f"\n{'═'*70}")
        print(f"GROUP: [{key}]  ({len(group)} videos)")
        print(f"{'─'*70}")

        for i, v in enumerate(group):
            marker = "NEWEST (keep?)" if i == len(group)-1 else f"OLDER  #{i+1}"
            print(f"\n  [{marker}]")
            print(f"  Title:   {v['title']}")
            print(f"  URL:     {v['url']}")
            print(f"  Views:   {v.get('views','0')} | Privacy: {v.get('privacy','?')}")
            print(f"  Date:    {fmt_date(v.get('published',''))}")

        print(f"\nOptions:")
        print(f"  d1..d{len(group)-1} = delete older video(s) e.g. 'd1' deletes oldest")
        print(f"  all              = delete all except newest")
        print(f"  s                = skip this group")
        print(f"  q                = quit cleanup")

        choice = input("\nYour choice: ").strip().lower()

        if choice == "q":
            break
        elif choice == "s":
            skipped += 1
            continue
        elif choice == "all":
            for v in group[:-1]:  # delete all except newest
                try:
                    youtube.videos().delete(id=v["id"]).execute()
                    print(f"  ✅ Deleted: {v['title'][:50]}")
                    deleted += 1
                except HttpError as e:
                    print(f"  ❌ Failed: {e}")
        elif choice.startswith("d"):
            try:
                idx = int(choice[1:]) - 1
                v   = group[idx]
                youtube.videos().delete(id=v["id"]).execute()
                print(f"  ✅ Deleted: {v['title'][:50]}")
                deleted += 1
            except (ValueError, IndexError):
                print("  Invalid choice, skipping.")
                skipped += 1

    print(f"\n{'═'*70}")
    print(f"✅ Cleanup complete!")
    print(f"   Deleted: {deleted} videos")
    print(f"   Skipped: {skipped} groups")

def cmd_delete_all(youtube):
    """Delete ALL videos from the channel — fresh start."""
    videos = get_all_videos(youtube)

    if not videos:
        print("✅ No videos found — channel is already empty!")
        return

    print(f"⚠️  This will permanently delete ALL {len(videos)} videos from your channel.")
    print(f"   This cannot be undone.")
    print("Videos that will be deleted:")
    for v in videos:
        print(f"  - {v['title'][:60]}")
        print(f"    {v['url']}")

    print("\nType 'DELETE ALL' to confirm: ", end="")
    confirm = input().strip()
    if confirm != "DELETE ALL":
        print("Cancelled — nothing deleted.")
        return

    print(f"\n🗑️  Deleting {len(videos)} videos...")
    deleted = 0
    failed  = 0
    for v in videos:
        try:
            youtube.videos().delete(id=v["id"]).execute()
            print(f"  ✅ Deleted: {v['title'][:55]}")
            deleted += 1
        except HttpError as e:
            print(f"  ❌ Failed: {v['title'][:40]} — {e}")
            failed += 1

    print(f"\n{'─'*55}")
    print(f"✅ Deleted: {deleted} videos")
    if failed:
        print(f"❌ Failed:  {failed} videos")

    # Reset upload log
    print("\n🔄 Resetting uploaded_games.json...")
    with open("uploaded_games.json", "w") as f:
        json.dump([], f)
    print("✅ Upload log cleared!")
    print("\n💡 Now commit the reset log:")
    print("   git add uploaded_games.json")
    print("   git commit -m 'Fresh start — reset upload log'")
    print("   git push origin main")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "help":
        print(f"""
YouTube Content Manager — {CHANNEL_NAME}

Commands:
  python manage_youtube.py list              List all your videos
  python manage_youtube.py dupes            Find duplicate videos + save report
  python manage_youtube.py delete <ID>       Delete a specific video by ID
  python manage_youtube.py cleanup          Interactive duplicate cleanup

Examples:
  python manage_youtube.py dupes
  python manage_youtube.py delete abc123XYZ
  python manage_youtube.py cleanup
""")
        return

    youtube = get_youtube()

    if cmd == "list":
        cmd_list(youtube)
    elif cmd == "dupes":
        cmd_dupes(youtube)
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("❌ Usage: python manage_youtube.py delete <VIDEO_ID>")
            sys.exit(1)
        cmd_delete(youtube, sys.argv[2])
    elif cmd == "cleanup":
        cmd_cleanup(youtube)
    elif cmd == "delete_all":
        cmd_delete_all(youtube)
    else:
        print(f"❌ Unknown command: {cmd}")
        print("   Run: python manage_youtube.py help")

if __name__ == "__main__":
    main()
