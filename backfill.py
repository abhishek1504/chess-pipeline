"""
backfill.py — One-time backfill for historical won games
The Thinking Athlete Pipeline

Unlike watcher.py (last 24h), this fetches ALL wins
from a specific year/month range and processes them.

Run locally on your Mac — not on GitHub Actions.

Usage:
    python backfill.py              # fetches all 2026 wins
    python backfill.py 2025         # fetches all 2025 wins
    python backfill.py 2026 06      # fetches June 2026 only
"""

import requests
import json
import os
import sys
import time
from datetime import datetime

USERNAME    = "abhi15041984"
HEADERS     = {"User-Agent": "TheThinkingAthlete/1.0 Chess Pipeline"}
OUTPUT_FILE = "won_games.json"
ABANDONMENT = {"abandoned", "timeout", "timevsinsufficient"}

def get_my_side(game):
    return "white" if game["white"]["username"].lower() == USERNAME.lower() else "black"

def is_real_win(game):
    side     = get_my_side(game)
    opp_side = "black" if side == "white" else "white"
    return game[side]["result"] == "win" and \
           game[opp_side]["result"] not in ABANDONMENT

def get_archives():
    url = f"https://api.chess.com/pub/player/{USERNAME}/games/archives"
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    return res.json()["archives"]

def get_games(archive_url, retries=3):
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

def main():
    # Parse args
    filter_year  = sys.argv[1] if len(sys.argv) > 1 else "2026"
    filter_month = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"🔍 Backfill: fetching wins for {filter_year}{f'/{filter_month}' if filter_month else ''}")
    print(f"   Username: {USERNAME}\n")

    archives = get_archives()

    # Filter archives by year/month
    filtered = []
    for url in archives:
        parts = url.split("/")
        year, month = parts[-2], parts[-1]
        if year == filter_year:
            if filter_month is None or month == filter_month.zfill(2):
                filtered.append((url, year, month))

    if not filtered:
        print(f"❌ No archives found for {filter_year}{f'/{filter_month}' if filter_month else ''}")
        print(f"   Available years: {list(set(u.split('/')[-2] for u in archives))}")
        sys.exit(1)

    print(f"📦 Found {len(filtered)} monthly archive(s) to process\n")

    all_wins    = []
    total_games = 0

    for archive_url, year, month in filtered:
        month_name = datetime(int(year), int(month), 1).strftime("%B %Y")
        print(f"  📅 {month_name}...", end=" ", flush=True)

        games       = get_games(archive_url)
        total_games += len(games)
        wins        = [g for g in games if is_real_win(g)]
        all_wins.extend(wins)

        print(f"{len(games)} games, {len(wins)} wins ✅")
        time.sleep(0.5)

    # Sort newest first
    all_wins.sort(key=lambda g: g.get("end_time", 0), reverse=True)

    print(f"\n{'─'*50}")
    print(f"📊 Total games scanned: {total_games}")
    print(f"🏆 Real wins found:     {len(all_wins)}")
    print(f"{'─'*50}\n")

    if not all_wins:
        print("😴 No wins found for this period.")
        return

    # Show preview
    print(f"First 10 wins:\n")
    for i, g in enumerate(all_wins[:10]):
        side       = get_my_side(g)
        opp_side   = "black" if side == "white" else "white"
        my_r       = g[side]["rating"]
        opp_name   = g[opp_side]["username"]
        opp_r      = g[opp_side]["rating"]
        tc         = g.get("time_class", "?")
        dt         = datetime.fromtimestamp(g["end_time"]).strftime("%Y-%m-%d %H:%M")
        print(f"  {i+1:03d}. vs {opp_name} ({opp_r}) | Me: {my_r} | {tc} | {dt}")

    if len(all_wins) > 10:
        print(f"  ... and {len(all_wins)-10} more")

    # Skip confirmation if running in GitHub Actions
    auto_mode = os.environ.get("BACKFILL_AUTO", "false").lower() == "true"
    if not auto_mode:
        print(f"\n⚠️  This will overwrite {OUTPUT_FILE} with {len(all_wins)} games.")
        confirm = input("Continue? (y/n): ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return
    else:
        print(f"\n✅ Auto mode — saving {len(all_wins)} games...")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_wins, f, indent=2)

    print(f"\n💾 Saved {len(all_wins)} games to {OUTPUT_FILE}")
    print(f"\n▶️  Now run:")
    print(f"   python step2_generate_video.py")
    print(f"   python step3_generate_scripts.py")
    print(f"   python step5_upload_youtube.py")

if __name__ == "__main__":
    main()
