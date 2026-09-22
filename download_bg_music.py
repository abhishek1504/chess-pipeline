"""
download_bg_music.py — Auto-download a Random Copyright-Free Track
The Thinking Athlete Pipeline — Long-Form Content

Uses the Jamendo API (free, no attribution required for most tracks).
Jamendo is a platform built specifically for Creative Commons / free music.

Setup (one time):
  1. Register free at https://devportal.jamendo.com/
  2. Create an app → copy the Client ID
  3. Add as GitHub Secret: JAMENDO_CLIENT_ID
  4. For local runs: export JAMENDO_CLIENT_ID=your_id

Output: sounds/longform_bg.mp3  (picked up automatically by the video generator)

Usage:
    python download_bg_music.py                      # skip if already exists
    python download_bg_music.py --force              # always re-download
    python download_bg_music.py --genre dhol         # specific search term
    JAMENDO_CLIENT_ID=xxx python download_bg_music.py
"""

import requests
import os
import random
import sys
import argparse
import json

JAMENDO_API  = "https://api.jamendo.com/v3.0/tracks/"
OUTPUT_PATH  = os.path.join("sounds", "longform_bg.mp3")
CACHE_DIR    = os.path.join("sounds", "music_cache")
CACHE_INDEX  = os.path.join(CACHE_DIR, "index.json")

# Search terms tried in order — first that returns ≥1 result wins.
# Mix of Punjabi-specific → broader Indian → world music as fallback.
DEFAULT_SEARCH_ORDER = [
    "bhangra",
    "punjabi folk",
    "dhol",
    "indian folk",
    "tabla",
    "bollywood instrumental",
    "world music",
]

MIN_FILE_BYTES = 50_000   # reject downloads smaller than 50 KB (likely errors)


def fetch_tracks(client_id, query, limit=30):
    """Search Jamendo for tracks matching query. Returns list of track dicts."""
    params = {
        "client_id":     client_id,
        "format":        "json",
        "limit":         str(limit),
        "search":        query,
        "audioformat":   "mp32",      # 320 kbps MP3
        "order":         "popularity_total",
        "include":       "musicinfo",
    }
    try:
        r = requests.get(JAMENDO_API, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        tracks = data.get("results", [])
        # Keep only tracks that have a direct download URL
        return [t for t in tracks if t.get("audiodownload") or t.get("audio")]
    except Exception as e:
        print(f"  ⚠️  Jamendo search failed for '{query}': {e}")
        return []


def download_track(url, dest_path):
    """Download audio from url → dest_path. Returns True on success."""
    try:
        r = requests.get(url, timeout=90, stream=True)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=16_384):
                f.write(chunk)
        if os.path.getsize(dest_path) < MIN_FILE_BYTES:
            os.remove(dest_path)
            return False
        return True
    except Exception as e:
        print(f"  ⚠️  Download error: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def load_cache_index():
    if os.path.exists(CACHE_INDEX):
        try:
            return json.load(open(CACHE_INDEX))
        except Exception:
            pass
    return []


def save_cache_index(index):
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(index, open(CACHE_INDEX, "w"), indent=2)


def pick_from_cache():
    """Pick a random cached track and copy to OUTPUT_PATH. Returns True if one found."""
    index = load_cache_index()
    valid = [e for e in index if os.path.exists(e["path"])]
    if not valid:
        return False
    entry = random.choice(valid)
    import shutil
    shutil.copy2(entry["path"], OUTPUT_PATH)
    print(f"  🎵 Using cached: {entry['name']} by {entry['artist']}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force",  action="store_true",
                        help="Re-download even if sounds/longform_bg.mp3 already exists")
    parser.add_argument("--genre",  type=str, default="",
                        help="Override search term (e.g. 'dhol', 'tabla', 'bhangra')")
    args, _ = parser.parse_known_args()

    # If not forced and file already exists, nothing to do
    if not args.force and os.path.exists(OUTPUT_PATH) and \
            os.path.getsize(OUTPUT_PATH) > MIN_FILE_BYTES:
        sz = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
        print(f"✅ Background music already present: {OUTPUT_PATH} ({sz:.1f} MB)")
        print("   Use --force to re-download.")
        return

    client_id = os.environ.get("JAMENDO_CLIENT_ID", "").strip()

    # ── No API key: try cache, then give up gracefully ────────────────────────
    if not client_id:
        print("ℹ️  JAMENDO_CLIENT_ID not set.")
        if pick_from_cache():
            print(f"   Output: {OUTPUT_PATH}")
            return
        print("   No cached tracks either.")
        print("   Pipeline will run without background music.")
        print("   To enable: register free at https://devportal.jamendo.com/")
        print("   and set JAMENDO_CLIENT_ID as a GitHub secret (or env var).")
        return

    # ── Build search order ────────────────────────────────────────────────────
    search_order = ([args.genre] + DEFAULT_SEARCH_ORDER) if args.genre else DEFAULT_SEARCH_ORDER

    print(f"🎵 Fetching music from Jamendo...")

    tracks = []
    used_query = ""
    for query in search_order:
        print(f"  🔍 Searching: '{query}' ...", end=" ", flush=True)
        tracks = fetch_tracks(client_id, query)
        if tracks:
            print(f"{len(tracks)} tracks found")
            used_query = query
            break
        print("none")

    if not tracks:
        print("  ⚠️  No tracks found. Pipeline continues without background music.")
        return

    # ── Pick a random track and download ─────────────────────────────────────
    random.shuffle(tracks)
    os.makedirs("sounds", exist_ok=True)

    for track in tracks[:5]:   # try up to 5 candidates
        name       = track.get("name", "Unknown")
        artist     = track.get("artist_name", "Unknown")
        dl_url     = track.get("audiodownload") or track.get("audio", "")
        duration   = track.get("duration", 0)
        license_cc = track.get("license_ccurl", "")

        if not dl_url:
            continue

        print(f"\n  🎼 Picked: {name}")
        print(f"     Artist:   {artist}")
        print(f"     Duration: {duration}s")
        print(f"     License:  {license_cc or 'CC (Jamendo)'}")
        print(f"     Query:    '{used_query}'")

        # Download directly to output path
        tmp_path = OUTPUT_PATH + ".tmp"
        if download_track(dl_url, tmp_path):
            os.replace(tmp_path, OUTPUT_PATH)
            sz = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
            print(f"  ✅ Saved: {OUTPUT_PATH}  ({sz:.1f} MB)")

            # Update local cache
            cache_filename = f"{artist}_{name}.mp3".replace("/", "_").replace(" ", "_")[:80]
            cache_path     = os.path.join(CACHE_DIR, cache_filename)
            os.makedirs(CACHE_DIR, exist_ok=True)
            import shutil
            shutil.copy2(OUTPUT_PATH, cache_path)

            index = load_cache_index()
            if not any(e["path"] == cache_path for e in index):
                index.append({
                    "name":    name,
                    "artist":  artist,
                    "path":    cache_path,
                    "query":   used_query,
                    "license": license_cc,
                })
                save_cache_index(index)
                print(f"  📦 Cached: {cache_path} ({len(index)} tracks in cache)")

            print(f"\n  🎵 Attribution (add to video description if required):")
            print(f"     '{name}' by {artist} — Jamendo / {license_cc or 'CC'}")
            return
        else:
            print(f"  ⚠️  Download failed, trying next track...")

    # All candidates failed — try cache
    if pick_from_cache():
        print(f"  📦 Fell back to cached track → {OUTPUT_PATH}")
    else:
        print("  ⚠️  All downloads failed. Pipeline continues without music.")


if __name__ == "__main__":
    main()
