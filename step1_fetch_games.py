import chess
import chess.pgn
"""
STEP 1 — Fetch ALL Won Games (All Time)
Filters:
  ✅ Abhishek won
  ❌ Skips games won by abandonment

The Thinking Athlete Pipeline
"""

import requests
import json
import time
from datetime import datetime

USERNAME    = "abhi15041984"
HEADERS     = {"User-Agent": "TheThinkingAthlete/1.0 Chess Pipeline"}
OUTPUT_FILE = "won_games.json"

# Result codes chess.com uses that mean opponent abandoned — not real games
ABANDONMENT_CODES = {"abandoned", "timeout", "timevsinsufficient"}

def get_archives():
    url = f"https://api.chess.com/pub/player/{USERNAME}/games/archives"
    res = requests.get(url, headers=HEADERS)
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
                print(f"    ⚠️  Retrying ({attempt+1}/{retries})...")
                time.sleep(2)
            else:
                print(f"    ❌ Failed: {e}")
                return []

def get_my_side(game):
    if game["white"]["username"].lower() == USERNAME.lower():
        return "white"
    return "black"


# ── Blunder detection ─────────────────────────────────────────────────────────

PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0
}
BLUNDER_THRESHOLD = 3   # losing 3+ points in one move = blunder (bishop or better)

def count_my_blunders(game_data):
    """
    Count blunders made by Abhishek in this game.
    A blunder = leaving a piece hanging worth 3+ points (bishop, rook, queen).
    Uses python-chess to simulate the game — no chess.com Game Review needed.
    Returns number of blunders.
    """
    pgn_text = game_data.get("pgn", "")
    if not pgn_text:
        return 0

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
    """Win by actual play — not abandonment/timeout."""
    side     = get_my_side(game)
    opp_side = "black" if side == "white" else "white"
    if game[side]["result"] != "win":
        return False, "not_win"
    # Check how opponent lost — skip abandonment
    opp_result = game[opp_side]["result"]
    if opp_result in ABANDONMENT_CODES:
        return False, "abandonment"
    # Quality filter — zero blunders only
    if count_my_blunders(game) > 0:
        return False, "blunder"
    return True, "ok"

def main():
    print(f"🔍 Fetching ALL archives for {USERNAME}")
    print(f"   Filter: Real wins only (no abandonment)\n")

    archives    = get_archives()
    total       = len(archives)
    print(f"📦 Found {total} monthly archives — fetching all...\n")

    passed      = []
    total_games = 0
    skipped_loss      = 0
    skipped_abandoned = 0

    for idx, archive_url in enumerate(archives):
        month = archive_url.split("/")[-2] + "/" + archive_url.split("/")[-1]
        print(f"  [{idx+1:03d}/{total}] {month} ", end="", flush=True)

        games        = get_games_from_archive(archive_url)
        total_games += len(games)

        month_wins = 0
        for game in games:
            ok, reason = is_real_win(game)
            if ok:
                passed.append(game)
                month_wins += 1
            elif reason == "abandonment":
                skipped_abandoned += 1
            else:
                skipped_loss += 1

        print(f"→ {len(games)} games, {month_wins} real wins ✅")
        time.sleep(0.3)

    print(f"\n{'─'*55}")
    print(f"📊 All time summary:")
    print(f"   Total games fetched:     {total_games}")
    print(f"   Skipped (loss/draw):     {skipped_loss}")
    print(f"   Skipped (abandonment):   {skipped_abandoned}")
    print(f"   ✅ Real wins:            {len(passed)}")
    print(f"{'─'*55}\n")

    if not passed:
        print("⚠️  No real wins found — check your username.")
        return

    # Filter to 2026 only
    from datetime import datetime
    passed_2026 = [g for g in passed
                   if datetime.fromtimestamp(g.get("end_time", 0)).year == 2026]
    passed = passed_2026

    # Sort newest first
    passed.sort(key=lambda g: g.get("end_time", 0), reverse=True)

    print(f"🏆 {len(passed)} real wins in 2026 (most recent first, showing first 20):\n")
    for i, g in enumerate(passed[:20]):
        side       = get_my_side(g)
        opp_side   = "black" if side == "white" else "white"
        my_rating  = g[side]["rating"]
        opp_name   = g[opp_side]["username"]
        opp_rating = g[opp_side]["rating"]
        time_class = g.get("time_class", "?")
        end_time   = datetime.fromtimestamp(g["end_time"]).strftime("%Y-%m-%d")
        print(f"  {i+1:03d}. vs {opp_name} ({opp_rating}) | "
              f"My rating: {my_rating} | "
              f"{time_class} | {end_time}")

    if len(passed) > 20:
        print(f"  ... and {len(passed)-20} more")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(passed, f, indent=2)

    print(f"\n💾 Saved {len(passed)} games to {OUTPUT_FILE}")
    print(f"▶️  Now run step2_generate_video.py!")

if __name__ == "__main__":
    main()
