"""
watcher.py — Fetch today's won games from chess.com
The Thinking Athlete Pipeline

Fetches games from the last 24 hours only.
Saves to won_games.json for step2 and step3 to process.

Run by GitHub Actions daily at 11 PM IST.
"""

import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone

USERNAME    = os.environ.get("CHESS_USERNAME", "abhi15041984")
HEADERS     = {"User-Agent": "TheThinkingAthlete/1.0 Chess Pipeline"}
OUTPUT_FILE = "won_games.json"

# Abandonment codes — skip these, not real games
ABANDONMENT_CODES = {"abandoned", "timeout", "timevsinsufficient"}

# How far back to look (24 hours)
LOOKBACK_HOURS = 24

def get_archives():
    url = f"https://api.chess.com/pub/player/{USERNAME}/games/archives"
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    return res.json()["archives"]

def get_games_from_archive(archive_url, retries=3):
    for attempt in range(retries):
        try:
            res = requests.get(archive_url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            return res.json().get("games", [])
        except Exception as e:
            if attempt < retries - 1:
                print(f"  ⚠️  Retry {attempt+1}/3...")
                time.sleep(3)
            else:
                print(f"  ❌ Failed: {e}")
                return []

def get_my_side(game):
    if game["white"]["username"].lower() == USERNAME.lower():
        return "white"
    return "black"

def is_real_win(game):
    side     = get_my_side(game)
    opp_side = "black" if side == "white" else "white"
    if game[side]["result"] != "win":
        return False
    if game[opp_side]["result"] in ABANDONMENT_CODES:
        return False
    return True

def main():
    now       = datetime.now(timezone.utc)
    cutoff    = now - timedelta(hours=LOOKBACK_HOURS)
    cutoff_ts = cutoff.timestamp()

    print(f"🔍 Fetching games for {USERNAME}")
    print(f"   Looking back {LOOKBACK_HOURS}h (since {cutoff.strftime('%Y-%m-%d %H:%M UTC')})\n")

    archives = get_archives()

    # Only check current month + previous month (in case run crosses midnight)
    recent_archives = archives[-2:] if len(archives) >= 2 else archives

    all_games   = []
    for archive_url in recent_archives:
        month = "/".join(archive_url.split("/")[-2:])
        print(f"📦 Fetching {month}...")
        games = get_games_from_archive(archive_url)
        all_games.extend(games)
        time.sleep(0.5)

    # Filter: last 24 hours + real wins only
    new_wins = [
        g for g in all_games
        if g.get("end_time", 0) >= cutoff_ts and is_real_win(g)
    ]

    # Sort newest first
    new_wins.sort(key=lambda g: g.get("end_time", 0), reverse=True)

    # Filter out already uploaded games using persistent log
    UPLOAD_LOG   = "uploaded_games.json"
    uploaded_ids = set()
    if os.path.exists(UPLOAD_LOG):
        try:
            uploaded_ids = set(json.load(open(UPLOAD_LOG)))
        except:
            uploaded_ids = set()

    def game_folder_id(game, idx):
        white = game["white"]["username"]
        black = game["black"]["username"]
        return f"game_{idx:03d}_{white}_vs_{black}"

    unduped  = []
    skipped  = 0
    for i, g in enumerate(new_wins):
        gid = game_folder_id(g, i+1)
        if gid in uploaded_ids:
            skipped += 1
        else:
            unduped.append(g)
    new_wins = unduped

    print(f"\n📊 Results:")
    print(f"   Games in last {LOOKBACK_HOURS}h: {sum(1 for g in all_games if g.get('end_time',0) >= cutoff_ts)}")
    print(f"   Real wins:        {len(new_wins) + skipped}")
    if skipped:
        print(f"   Already uploaded: {skipped} (skipped)")
    print(f"   New to process:   {len(new_wins)}")

    if not new_wins:
        print("\n😴 No new wins to process.")
        print("   Pipeline will stop here — no videos to generate.")
        with open(OUTPUT_FILE, "w") as f:
            json.dump([], f)
        return

    print(f"\n🏆 {len(new_wins)} new wins found:\n")
    for i, g in enumerate(new_wins):
        side       = get_my_side(g)
        opp_side   = "black" if side == "white" else "white"
        my_rating  = g[side]["rating"]
        opp_name   = g[opp_side]["username"]
        opp_rating = g[opp_side]["rating"]
        time_class = g.get("time_class", "?")
        end_time   = datetime.fromtimestamp(g["end_time"]).strftime("%H:%M")
        print(f"  {i+1}. vs {opp_name} ({opp_rating}) | My rating: {my_rating} | {time_class} | {end_time}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(new_wins, f, indent=2)

    print(f"\n💾 Saved {len(new_wins)} games to {OUTPUT_FILE}")
    print(f"▶️  step2 and step3 will now process these games.")

if __name__ == "__main__":
    main()
