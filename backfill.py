import chess
import chess.pgn
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



# ── Game quality estimation (accuracy proxy) ──────────────────────────────────
# Estimates game quality without chess.com Game Review
# Based on: blunders, mistakes, material hanging, move efficiency
#
# Quality score 0-100 (roughly maps to chess.com accuracy):
#   90-100 = excellent (≈ 90%+ accuracy)
#   75-89  = good      (≈ 75-90% accuracy)
#   60-74  = ok        (≈ 60-75% accuracy)  ← MIN_QUALITY default
#   below 60 = poor

MIN_QUALITY     = 70    # minimum quality score to upload (≈ 70% accuracy proxy)
PIECE_VALUES    = {
    chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3,
    chess.ROOK:5, chess.QUEEN:9, chess.KING:0
}

def estimate_game_quality(game_data):
    """
    Estimate game quality 0-100 as a proxy for chess.com accuracy.
    Analyses Abhishek's moves only.

    Penalties:
    - Hanging a queen  (9pts): -25 points
    - Hanging a rook   (5pts): -18 points
    - Hanging a bishop/knight (3pts): -12 points
    - Hanging a pawn   (1pt):  -4 points
    - Missing a free capture worth 5+: -8 points

    Score starts at 100, penalties applied per bad move.
    """
    pgn_text = game_data.get("pgn", "")
    if not pgn_text:
        return 100  # no data = don't penalise

    try:
        import chess.pgn as cpgn, io
        game     = cpgn.read_game(io.StringIO(pgn_text))
        if not game:
            return 100

        side     = get_my_side(game_data)
        my_color = chess.WHITE if side == "white" else chess.BLACK
        board    = game.board()
        score    = 100
        my_moves = 0

        for move in game.mainline_moves():
            is_my = (board.turn == my_color)

            if is_my:
                my_moves += 1

                # Check 1: Am I missing a free capture?
                best_free = 0
                for candidate in board.legal_moves:
                    if board.is_capture(candidate):
                        target = board.piece_at(candidate.to_square)
                        if target and target.color != my_color:
                            val = PIECE_VALUES.get(target.piece_type, 0)
                            # Check if it's safe to take
                            b2 = board.copy()
                            b2.push(candidate)
                            attacked = b2.is_attacked_by(
                                not my_color, candidate.to_square
                            )
                            if not attacked and val > best_free:
                                best_free = val

                board.push(move)

                # Penalty for missing free capture
                if best_free >= 5:
                    score -= 8
                elif best_free >= 3:
                    score -= 4

                # Check 2: Did I just hang a piece?
                for opp_mv in board.legal_moves:
                    if not board.is_capture(opp_mv):
                        continue
                    victim = board.piece_at(opp_mv.to_square)
                    if not victim or victim.color != my_color:
                        continue
                    val = PIECE_VALUES.get(victim.piece_type, 0)
                    if val == 0:
                        continue

                    # Can I recapture?
                    b2 = board.copy()
                    b2.push(opp_mv)
                    can_recap = any(
                        b2.is_capture(m) and b2.piece_at(m.to_square) and
                        b2.piece_at(m.to_square).color != my_color and
                        PIECE_VALUES.get(b2.piece_at(m.to_square).piece_type,0) >= val
                        for m in b2.legal_moves
                    )
                    if not can_recap:
                        # Penalty based on piece value
                        if val >= 9:   score -= 25
                        elif val >= 5: score -= 18
                        elif val >= 3: score -= 12
                        else:          score -= 4
                        break   # count once per move

            else:
                board.push(move)

        return max(0, min(100, score))

    except Exception:
        return 100  # parse error = don't penalise

    try:
        import chess.pgn, io
        game     = chess.pgn.read_game(io.StringIO(pgn_text))
        if not game:
            return 0

        side     = get_my_side(game_data)
        my_color = chess.WHITE if side == "white" else chess.BLACK
        board    = game.board()
        blunders = 0

        for move in game.mainline_moves():
            is_my_move = (board.turn == my_color)
            if is_my_move:
                # Check if I am leaving a piece hanging after this move
                board.push(move)
                # Look at all opponent responses — if any capture my piece for free
                for opp_move in board.legal_moves:
                    if board.is_capture(opp_move):
                        captured = board.piece_at(opp_move.to_square)
                        if captured and captured.color == my_color:
                            val = PIECE_VALUES.get(captured.piece_type, 0)
                            if val >= BLUNDER_THRESHOLD:
                                # Check if I can recapture
                                board2 = board.copy()
                                board2.push(opp_move)
                                can_recapture = any(
                                    board2.is_capture(m) and
                                    board2.piece_at(m.to_square) and
                                    board2.piece_at(m.to_square).color != my_color
                                    for m in board2.legal_moves
                                    if board2.piece_at(m.to_square) and
                                    PIECE_VALUES.get(board2.piece_at(m.to_square).piece_type,0) >= val
                                )
                                if not can_recapture:
                                    blunders += 1
                                    break   # count once per move
            else:
                board.push(move)

        return blunders

    except Exception:
        return 0   # if parsing fails, don't skip the game

def is_real_win(game):
    side     = get_my_side(game)
    opp_side = "black" if side == "white" else "white"
    if game[side]["result"] != "win":
        return False
    if game[opp_side]["result"] in ABANDONMENT:
        return False
    # Quality filter — estimated accuracy >= MIN_QUALITY
    quality = estimate_game_quality(game)
    if quality < MIN_QUALITY:
        return False
    # Quality filter
    if estimate_game_quality(game) < MIN_QUALITY:
        return False
    return True

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

    # Sort oldest first — chronological story for the channel
    all_wins.sort(key=lambda g: g.get("end_time", 0), reverse=False)

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

    # Filter out games already uploaded
    # Uses uploaded_games.json — a persistent log committed to the repo
    # This works on GitHub Actions where videos/ folder doesn't persist
    UPLOAD_LOG = "uploaded_games.json"
    uploaded_ids = set()
    if os.path.exists(UPLOAD_LOG):
        try:
            uploaded_ids = set(json.load(open(UPLOAD_LOG)))
        except:
            uploaded_ids = set()

    def game_id(game, idx):
        """Unique ID matching the game folder name written by step5."""
        white = game["white"]["username"]
        black = game["black"]["username"]
        return f"game_{idx:03d}_{white}_vs_{black}"

    # Check against upload log
    unprocessed  = []
    skipped_done = 0
    for i, g in enumerate(all_wins):
        if game_id(g, i+1) in uploaded_ids:
            skipped_done += 1
        else:
            unprocessed.append((i+1, g))

    if skipped_done:
        print(f"\n⏭️  Skipping {skipped_done} games already uploaded to YouTube")

    if not unprocessed:
        print("✅ All games for this period already uploaded! Nothing to do.")
        json.dump([], open(OUTPUT_FILE, "w"))
        return

    print(f"📋 {len(unprocessed)} games not yet uploaded")

    # Limit to MAX_UPLOADS
    max_uploads = int(os.environ.get("MAX_UPLOADS", 0))
    if max_uploads > 0 and len(unprocessed) > max_uploads:
        print(f"⚙️  Taking next {max_uploads} of {len(unprocessed)} unprocessed games")
        unprocessed = unprocessed[:max_uploads]

    # Rebuild all_wins with correct original indices preserved
    all_wins = [g for _, g in unprocessed]

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
