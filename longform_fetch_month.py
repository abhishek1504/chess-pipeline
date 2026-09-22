"""
longform_fetch_month.py — Fetch Filtered Wins for a Specific Month
The Thinking Athlete Pipeline — Long-Form Content

Filters applied (all must pass):
  1. Win by checkmate (CHECKMATE_ONLY=true, default)
  2. My accuracy ≥ MIN_ACCURACY % (default 80 %)
  3. Up to MAX_GAMES games kept (oldest-first, default 50; 0 = no limit)

Usage:
    YEAR=2026 MONTH=1 python longform_fetch_month.py
    python longform_fetch_month.py --year 2026 --month 1
    python longform_fetch_month.py --year 2026 --month 1 --min-accuracy 85 --max-games 30
"""

import requests
import json
import os
import sys
import time
import argparse
from datetime import datetime

USERNAME    = "abhi15041984"
HEADERS     = {"User-Agent": "TheThinkingAthlete/1.0 Chess Pipeline"}
OUTPUT_FILE = "monthly_wins.json"

ABANDONMENT_CODES = {"abandoned", "timevsinsufficient"}
CHECKMATE_ONLY    = os.environ.get("CHECKMATE_ONLY", "true").lower() == "true"
MIN_ACCURACY      = float(os.environ.get("MIN_ACCURACY", "80.0"))
MAX_GAMES         = int(os.environ.get("MAX_GAMES", "50") or 50)


def get_my_side(game):
    return "white" if game["white"]["username"].lower() == USERNAME.lower() else "black"


def my_accuracy(game):
    """Return my accuracy float, or None if not available."""
    side = get_my_side(game)
    acc  = game.get("accuracies", {})
    if not acc:
        return None
    val = acc.get(side)
    return float(val) if val is not None else None


def is_real_win(game, min_accuracy):
    side     = get_my_side(game)
    opp_side = "black" if side == "white" else "white"

    if game[side]["result"] != "win":
        return False, "not_win"

    opp_result = game[opp_side]["result"]
    if opp_result in ABANDONMENT_CODES:
        return False, "abandonment"

    if CHECKMATE_ONLY and opp_result != "checkmated":
        return False, f"not_checkmate({opp_result})"

    acc = my_accuracy(game)
    if acc is None:
        return False, "no_accuracy_data"
    if acc < min_accuracy:
        return False, f"low_accuracy({acc:.1f}%)"

    return True, "ok"


def fetch_monthly_wins(year, month, min_accuracy):
    url = f"https://api.chess.com/pub/player/{USERNAME}/games/{year}/{month:02d}"
    print(f"📦 Fetching {year}/{month:02d} from chess.com...")

    for attempt in range(3):
        try:
            res = requests.get(url, headers=HEADERS, timeout=20)
            if res.status_code == 404:
                print(f"⚠️  No archive found for {year}/{month:02d} (404)")
                return []
            res.raise_for_status()
            games = res.json().get("games", [])
            break
        except Exception as e:
            if attempt < 2:
                print(f"  ⚠️  Retry {attempt+1}/3...")
                time.sleep(3)
            else:
                print(f"  ❌ Failed: {e}")
                return []

    wins = []
    skip_counts = {}
    for game in games:
        ok, reason = is_real_win(game, min_accuracy)
        if ok:
            wins.append(game)
        else:
            bucket = reason.split("(")[0]
            skip_counts[bucket] = skip_counts.get(bucket, 0) + 1

    skip_summary = ", ".join(f"{v} {k}" for k, v in sorted(skip_counts.items()))
    print(f"   {len(games)} total games → {len(wins)} qualifying wins"
          f"  (skipped: {skip_summary or 'none'})")
    return wins


def main():
    year  = int(os.environ.get("YEAR",  0) or 0)
    month = int(os.environ.get("MONTH", 0) or 0)

    parser = argparse.ArgumentParser(description="Fetch monthly chess wins")
    parser.add_argument("--year",         type=int)
    parser.add_argument("--month",        type=int)
    parser.add_argument("--min-accuracy", type=float, default=None,
                        help="Minimum my accuracy %% to include a game (default 80)")
    parser.add_argument("--max-games",    type=int,   default=None,
                        help="Cap number of games kept (default 50; 0 = no limit)")
    args, _ = parser.parse_known_args()

    if args.year:  year  = args.year
    if args.month: month = args.month

    min_accuracy = args.min_accuracy if args.min_accuracy is not None else MIN_ACCURACY
    max_games    = args.max_games    if args.max_games    is not None else MAX_GAMES

    if not year or not month:
        print("❌ Provide YEAR and MONTH")
        print("   Example: YEAR=2026 MONTH=1 python longform_fetch_month.py")
        print("         or: python longform_fetch_month.py --year 2026 --month 1")
        sys.exit(1)

    if not (1 <= month <= 12):
        print(f"❌ Invalid month: {month}  (must be 1–12)")
        sys.exit(1)

    month_name = datetime(year, month, 1).strftime("%B %Y")
    print(f"🔍 Fetching wins for {month_name}")
    print(f"   Username:     {USERNAME}")
    print(f"   Filter:       {'checkmate wins only' if CHECKMATE_ONLY else 'all wins'}")
    print(f"   Min accuracy: {min_accuracy:.0f}%")
    print(f"   Max games:    {max_games if max_games else 'no limit'}\n")

    wins = fetch_monthly_wins(year, month, min_accuracy)

    # Oldest first — chronological order in the compilation
    wins.sort(key=lambda g: g.get("end_time", 0))

    # Cap
    if max_games and len(wins) > max_games:
        print(f"✂️  Keeping first {max_games} of {len(wins)} qualifying wins")
        wins = wins[:max_games]

    print(f"\n{'═'*62}")
    print(f"🏆  {len(wins)} games selected for {month_name}")
    print(f"{'═'*62}")

    for i, g in enumerate(wins):
        side       = get_my_side(g)
        opp_side   = "black" if side == "white" else "white"
        my_rating  = g[side]["rating"]
        opp_name   = g[opp_side]["username"]
        opp_rating = g[opp_side]["rating"]
        opp_result = g[opp_side]["result"]
        tc         = g.get("time_class", "?")
        dt         = datetime.fromtimestamp(g["end_time"]).strftime("%b %d")
        acc        = my_accuracy(g)
        acc_str    = f"{acc:.0f}%" if acc is not None else "  -"
        print(f"  {i+1:02d}. vs {opp_name:20s} ({opp_rating})  "
              f"acc:{acc_str:4s}  my:{my_rating}  {opp_result:12s}  {tc}  {dt}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(wins, f, indent=2)

    print(f"\n💾  Saved {len(wins)} games → {OUTPUT_FILE}")

    if not wins:
        print("😴  No qualifying wins found.  Pipeline stops here.")
        sys.exit(1)

    print(f"▶️   Next: python longform_generate_video.py --year {year} --month {month}")


if __name__ == "__main__":
    main()
